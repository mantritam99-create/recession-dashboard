"""Raw data -> a 0-100 stress score per indicator, via historical PERCENTILE.

The core design choice (per the brief): never use absolute thresholds for the
score. A CAPE of 39 is meaningless until you know it's the 98th percentile of all
readings since 1881. `direction` flips series where LOW is the stressful end
(an inverted yield curve, falling sentiment).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import CFG
from data import fetch_fred, fetch_market, fetch_valuation, fetch_manual

MIN_HIST = 30  # need at least this many observations to trust a percentile


def percentile_score(current, history, direction: str = "high"):
    """% of historical readings below `current`, flipped if low values are stressful."""
    if current is None:
        return None
    h = pd.Series(history).dropna()
    if len(h) < MIN_HIST:
        return None
    pct = float((h < current).mean() * 100.0)
    return pct if direction == "high" else 100.0 - pct


def percentile_asof(series, asof, direction: str = "high"):
    """Date-causal score: percentile of the as-of value vs ONLY prior rows.

    This prevents future-row lookahead. It does not make latest-vintage source data
    vintage-correct. Returns (current_value, stress_score) or (None, None).
    """
    if series is None:
        return None, None
    s = series[series.index <= asof].dropna()
    if len(s) < MIN_HIST:
        return None, None
    cur = float(s.iloc[-1])
    pct = float((s < cur).mean() * 100.0)
    return cur, (pct if direction == "high" else 100.0 - pct)


def _last(s):
    return float(s.iloc[-1]) if s is not None and len(s) else None


def load_all(revision_adjusted: bool = False):
    """Fetch every indicator once; optionally enforce the backtest revision policy."""
    return [(spec, _load(spec, revision_adjusted)) for spec in _specs()]


def apply_revision_policy(series, key: str):
    """Delay latest-vintage data by its configured conservative availability lag."""
    if series is None or not CFG["revisions_policy"]["enforced"]:
        return series
    rule = CFG["revisions_policy"]["series"].get(key)
    if rule is None:
        raise ValueError(f"missing revisions_policy classification for {key}")
    lag = int(rule["lag_months"])
    if lag <= 0:
        return series
    delayed = series.copy()
    delayed.index = pd.DatetimeIndex(delayed.index) + pd.DateOffset(months=lag)
    return delayed.sort_index()


def load_raw_data() -> dict:
    """Raw series keyed by id (FRED code / ticker / 'cape' / 'buffett') for the V3
    feature registry (features.compute_features). Returns TRULY raw levels — no yoy
    transform applied here (the registry owns transforms), and includes context
    tickers (^GSPC/^TNX/DX-Y.NYB/NVDA) that are excluded from the scored composite."""
    out = {}
    for sid in CFG["fred_series"]:
        out[sid] = fetch_fred.series(sid)            # raw level (CPI stays an index; registry does yoy)
    for tkr in CFG["market_tickers"]:
        out[tkr] = fetch_market.history(tkr)
    out["cape"] = fetch_valuation.cape_history()
    out["buffett"] = fetch_valuation.buffett_history()
    return out


def _specs():
    specs = []
    for sid, m in CFG["fred_series"].items():
        specs.append({**m, "key": sid, "src": "fred"})
    for tkr, m in CFG["market_tickers"].items():
        if m["bucket"] in CFG["weights"]:        # only scored buckets (e.g. VIX -> sentiment)
            specs.append({**m, "key": tkr, "src": "market"})
    for k, m in CFG["valuation"].items():
        specs.append({**m, "key": k, "src": "val_" + k})
    return specs


def _load(spec, revision_adjusted=False):
    src = spec["src"]
    if src == "fred":
        s = fetch_fred.series(spec["key"], allow_stale=revision_adjusted)
        if s is not None and spec.get("transform") == "yoy":
            s = fetch_fred.yoy(s)
        return apply_revision_policy(s, spec["key"]) if revision_adjusted else s
    if src == "market":
        s = fetch_market.history(spec["key"])
        return apply_revision_policy(s, spec["key"]) if revision_adjusted else s
    if src == "val_cape":
        s = fetch_valuation.cape_history()
        return apply_revision_policy(s, spec["key"]) if revision_adjusted else s
    if src == "val_buffett":
        s = fetch_valuation.buffett_history(allow_stale=revision_adjusted)
        return apply_revision_policy(s, spec["key"]) if revision_adjusted else s
    return None


def compute(loaded=None) -> list[dict]:
    """One row per indicator: current value, stress score, history depth, ok flag."""
    loaded = load_all() if loaded is None else loaded
    rows = []
    for spec, s in loaded:
        cur = _last(s)
        score = percentile_score(cur, s, spec["direction"])
        asof = s.index.max().date().isoformat() if (s is not None and len(s)) else None
        rows.append({
            "name": spec["name"], "bucket": spec["bucket"], "direction": spec["direction"],
            "current": cur, "score": score, "n": (len(s) if s is not None else 0),
            "ok": score is not None, "source": "live", "stale": False, "asof": asof,
        })
    # AI-bubble + manual sentiment layer (scored by calm/stress anchors, not percentile)
    for m in fetch_manual.load():
        rows.append({
            "name": m["name"], "bucket": m["bucket"], "direction": "high",
            "current": m["value"], "score": m["score"], "n": 1,
            "ok": True, "source": "manual", "stale": m["stale"],
            "asof": m["date"].isoformat() if m.get("date") else None,
        })
    return rows


if __name__ == "__main__":
    for r in compute():
        sc = f"{r['score']:5.1f}" if r["ok"] else "  -- "
        cur = f"{r['current']:.2f}" if r["current"] is not None else "n/a"
        print(f"{r['name']:26s} {r['bucket']:13s} cur={cur:>10s}  stress={sc}  (n={r['n']})")
