"""3-bucket weighted composite + breadth adjustment.

composite     = weighted mean of bucket stress scores (weights from config.yaml,
                renormalized over whichever buckets have live data)
breadth       = share of live indicators sitting in the danger zone (>75)
confidence    = composite * (0.5 + 0.5*breadth)   <- the brief's refinement:
                a high score driven by ONE screaming indicator is downweighted;
                broad agreement is required for full conviction.
margin (+/-)  = widens as data coverage drops or whole buckets go missing,
                forcing intellectual honesty about how much we actually know.
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import CFG
from model import indicators

WEIGHTS = CFG["weights"]
DZ = CFG["breadth"]["danger_zone"]


def composite(rows=None) -> dict:
    rows = indicators.compute() if rows is None else rows
    ok = [r for r in rows if r["ok"]]
    weights = CFG["weights"]
    dz = CFG["breadth"]["danger_zone"]

    # bucket score = staleness-WEIGHTED mean of its live members (a flagged-stale
    # indicator keeps only stale_weight of its vote, so a frozen value can't hold
    # the bucket where it was last read).
    sw = CFG.get("staleness", {}).get("stale_weight", 1.0)
    bucket = {}
    for b in weights:
        members = [r for r in ok if r["bucket"] == b]
        iw = sum((sw if r.get("stale") else 1.0) for r in members)
        bucket[b] = (sum(r["score"] * (sw if r.get("stale") else 1.0) for r in members) / iw) if iw else None

    # renormalize weights across buckets that actually have data
    avail = {b: w for b, w in weights.items() if bucket[b] is not None}
    wsum = sum(avail.values()) or 1.0
    comp = sum(bucket[b] * w / wsum for b, w in avail.items()) if avail else 0.0

    breadth = (sum(1 for r in ok if r["score"] >= dz) / len(ok)) if ok else 0.0
    confidence = comp * (0.5 + 0.5 * breadth)

    stale = [r["name"] for r in ok if r.get("stale")]
    coverage = len(ok) / len(rows) if rows else 0.0
    missing = [b for b in weights if bucket[b] is None]
    margin = round(4 + 16 * (1 - coverage) + 6 * len(missing) + 3 * len(stale), 1)

    return {
        "bucket": {b: (round(v, 1) if v is not None else None) for b, v in bucket.items()},
        "weights_used": {b: round(w / wsum, 2) for b, w in avail.items()},
        "composite": round(comp, 1),
        "breadth": round(breadth, 2),
        "confidence": round(confidence, 1),
        "margin": margin,
        "coverage": round(coverage, 2),
        "n_live": len(ok), "n_total": len(rows),
        "danger": [r["name"] for r in ok if r["score"] >= dz],
        "missing_buckets": missing,
        "stale": stale,
    }


# ---------------------------------------------------------------------------
#  MOMENTUM  — "how the world is moving", not just where it is.
#  All point-in-time (series only; the manual layer has no history yet).
# ---------------------------------------------------------------------------
def composite_asof(loaded, asof) -> dict:
    """Series-only weighted composite as-of a date (no lookahead). Used by trend + backtest."""
    per = {b: [] for b in WEIGHTS}
    n_live = n_danger = 0
    for spec, s in loaded:
        if spec["bucket"] not in WEIGHTS:
            continue
        _, score = indicators.percentile_asof(s, asof, spec["direction"])
        if score is None:
            continue
        per[spec["bucket"]].append(score)
        n_live += 1
        n_danger += score >= DZ
    bucket = {b: (sum(v) / len(v) if v else None) for b, v in per.items()}
    avail = {b: w for b, w in WEIGHTS.items() if bucket[b] is not None}
    wsum = sum(avail.values()) or 1.0
    comp = sum(bucket[b] * w / wsum for b, w in avail.items()) if avail else None
    breadth = (n_danger / n_live) if n_live else 0.0
    conf = comp * (0.5 + 0.5 * breadth) if comp is not None else None
    return {"composite": comp, "confidence": conf, "breadth": breadth, "bucket": bucket}


def _eom(base_period, months_back):
    return (base_period - months_back).to_timestamp(how="end")


def composite_history(loaded=None, months=12, asof=None) -> list[tuple]:
    """[(date, composite), ...] for the last `months` month-ends — the trajectory."""
    loaded = indicators.load_all() if loaded is None else loaded
    base = (pd.Timestamp(datetime.date.today()) if asof is None else pd.Timestamp(asof)).to_period("M")
    out = []
    for k in range(months - 1, -1, -1):
        d = _eom(base, k)
        out.append((d.date(), composite_asof(loaded, d)["composite"]))
    return out


def trend(loaded=None, asof=None) -> dict:
    """Composite now vs 1/3/6 months ago + the signed deltas (direction & acceleration)."""
    loaded = indicators.load_all() if loaded is None else loaded
    base = (pd.Timestamp(datetime.date.today()) if asof is None else pd.Timestamp(asof)).to_period("M")
    pts = {k: composite_asof(loaded, _eom(base, k))["composite"] for k in (0, 1, 3, 6)}
    now = pts[0]
    return {
        "now": now, "m1": pts[1], "m3": pts[3], "m6": pts[6],
        "d1": (now - pts[1]) if now is not None and pts[1] is not None else None,
        "d3": (now - pts[3]) if now is not None and pts[3] is not None else None,
    }


def indicator_deltas(loaded=None, asof=None, lookback=3) -> dict:
    """{indicator_name: stress change over `lookback` months} — what's moving most."""
    loaded = indicators.load_all() if loaded is None else loaded
    base = (pd.Timestamp(datetime.date.today()) if asof is None else pd.Timestamp(asof)).to_period("M")
    past = _eom(base, lookback)
    now_d = _eom(base, 0)
    out = {}
    for spec, s in loaded:
        _, now = indicators.percentile_asof(s, now_d, spec["direction"])
        _, then = indicators.percentile_asof(s, past, spec["direction"])
        if now is not None and then is not None:
            out[spec["name"]] = round(now - then, 1)
    return out


def _selfcheck_staleness():
    """A stale indicator must pull its bucket less than the same value fresh."""
    base = lambda stale: [
        {"name": "hi", "bucket": "valuation", "score": 90, "ok": True, "stale": False},
        {"name": "lo", "bucket": "valuation", "score": 10, "ok": True, "stale": stale},  # low one decays when stale
    ]
    fresh = composite(base(False))["bucket"]["valuation"]   # mean(90,10)=50
    stale = composite(base(True))["bucket"]["valuation"]    # 10 down-weighted -> >50
    assert stale > fresh, f"staleness decay broken: stale={stale} !> fresh={fresh}"
    print(f"  [selfcheck] staleness decay OK (fresh bucket={fresh:.1f}, with stale low={stale:.1f})")


if __name__ == "__main__":
    _selfcheck_staleness()
    c = composite()
    print(f"composite={c['composite']}  confidence={c['confidence']} +/-{c['margin']}  "
          f"breadth={c['breadth']}  coverage={c['coverage']}")
    print("buckets:", c["bucket"], "weights:", c["weights_used"])
    print("danger zone:", ", ".join(c["danger"]) or "none")
