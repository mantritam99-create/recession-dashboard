"""Reusable analytics layer for the dashboard components (shared engine).

Everything point-in-time (no lookahead), computed from the same `load_all()` set
so US and a future India build stay in sync. Keep dashboard.py to rendering only.
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np
from config import CFG
from model import indicators, scoring
from data import fetch_market

TODAY = datetime.date.today
BANDS = CFG["bands"]["composite"]

# NBER US recessions (for trajectory shading)
NBER_RECESSIONS = [("2001-03-01", "2001-11-30"),
                   ("2007-12-01", "2009-06-30"),
                   ("2020-02-01", "2020-04-30")]

# indicator -> evidence family (for the sortable/filterable table)
FAMILY = {
    "Shiller CAPE": "valuation", "Buffett Indicator": "valuation",
    "3M-10Y spread": "macro", "2s10s spread": "macro", "Core CPI (YoY calc)": "macro",
    "WTI crude": "macro", "Hyperscaler capex QoQ%": "macro", "NVDA inventory days": "macro",
    "High-yield OAS": "credit", "IG credit spread": "credit",
    "Bank lending standards": "credit", "Credit card delinquency": "credit",
    "AI-infra credit spread": "credit",
    "Sahm Rule": "labor", "Initial jobless claims": "labor",
    "VIX": "liquidity", "Margin debt YoY%": "liquidity",
    "U.Mich sentiment": "sentiment", "Personal savings rate": "sentiment",
    "Insider buy/sell ratio": "sentiment", "AAII bull-bear spread": "sentiment",
}


def family_of(name: str) -> str:
    return FAMILY.get(name, "other")


def _eom(p): return p.to_timestamp(how="end")


def composite_series(loaded=None, start="1999-01-01") -> list:
    """[(date, composite), ...] monthly — the long-run trajectory (series-only, no lookahead)."""
    loaded = indicators.load_all() if loaded is None else loaded
    dates = pd.date_range(start, pd.Timestamp(TODAY()), freq="MS")
    out = []
    for d in dates:
        c = scoring.composite_asof(loaded, _eom(d.to_period("M")))["composite"]
        out.append((d.date(), c))
    return out


def contributions(c: dict) -> list:
    """Bucket point-contributions to the composite (weight x score); they sum to it."""
    out = []
    for b, w in c["weights_used"].items():
        v = c["bucket"].get(b)
        if v is not None:
            out.append({"bucket": b, "points": round(w * v, 1), "weight": w, "score": v})
    return sorted(out, key=lambda x: -x["points"])


def gauge(tw: dict, current):
    """Distance-to-trip: fill fraction from floor -> trigger, plus tripped flag."""
    if current is None:
        return None
    floor, trig = tw["floor"], tw["level"]
    if tw["trips_when"] == "above":
        frac = (current - floor) / (trig - floor) if trig != floor else 0.0
        tripped = current >= trig
    else:  # 'below' (e.g. yield curve): closer to a low/negative trigger = more fill
        frac = (floor - current) / (floor - trig) if floor != trig else 0.0
        tripped = current <= trig
    return {"fill": max(0.0, min(1.0, frac)), "tripped": tripped, "floor": floor, "trigger": trig}


def indicator_sparklines(loaded=None, months=18) -> dict:
    """{indicator_name: [stress, ...]} recent monthly stress, for inline sparklines."""
    loaded = indicators.load_all() if loaded is None else loaded
    base = pd.Timestamp(TODAY()).to_period("M")
    dates = [_eom(base - k) for k in range(months - 1, -1, -1)]
    out = {}
    for spec, s in loaded:
        vals = [indicators.percentile_asof(s, d, spec["direction"])[1] for d in dates]
        if any(v is not None for v in vals):
            out[spec["name"]] = [round(v, 1) if v is not None else None for v in vals]
    return out


def freshness(rows: list) -> dict:
    """Data-quality header: coverage %, stale count, per-input vintage."""
    ok = [r for r in rows if r["ok"]]
    items = [{"name": r["name"], "asof": r.get("asof"), "source": r["source"],
              "stale": bool(r.get("stale")), "family": family_of(r["name"])}
             for r in rows]
    return {"coverage": (len(ok) / len(rows) if rows else 0.0),
            "n_live": len(ok), "n_total": len(rows),
            "stale": [r["name"] for r in ok if r.get("stale")],
            "items": sorted(items, key=lambda x: (x["asof"] or ""))}


# ===========================================================================
#  HEAVIER ANALYTICS (Checkpoint 2) — empirical, honesty-guarded.
# ===========================================================================
NBER_STARTS = ["2001-03-01", "2007-12-01", "2020-02-01"]
COMP_BUCKETS = [(-1, 55, "<55"), (55, 65, "55-65"), (65, 70, "65-70"), (70, 200, "70+")]


def _bucket_of(v):
    for lo, hi, lbl in COMP_BUCKETS:
        if lo <= v < hi:
            return lbl
    return None


def _series_by_name(loaded, name):
    for spec, s in loaded:
        if spec["name"] == name:
            return s
    return None


def stress_matrix(loaded=None, start="2000-01-01") -> pd.DataFrame:
    """months x series-indicators matrix of stress scores (point-in-time)."""
    loaded = indicators.load_all() if loaded is None else loaded
    dates = pd.date_range(start, pd.Timestamp(TODAY()), freq="MS")
    cols = {}
    for spec, s in loaded:
        cols[spec["name"]] = [indicators.percentile_asof(s, _eom(d.to_period("M")), spec["direction"])[1]
                              for d in dates]
    return pd.DataFrame(cols, index=[d.date() for d in dates])


def forward_returns(loaded=None, start="1999-01-01") -> list:
    """Composite bucket -> realized avg fwd-12m S&P return (+ N). Empirical, no lookahead in composite."""
    loaded = indicators.load_all() if loaded is None else loaded
    comp = composite_series(loaded, start)
    spx = fetch_market.history("^GSPC")
    if spx is None:
        return []
    spx_m = spx.resample("ME").last()
    last = spx_m.index.max()
    data = {lbl: [] for _, _, lbl in COMP_BUCKETS}
    for d, v in comp:
        if v is None:
            continue
        d0 = pd.Timestamp(d); d1 = d0 + pd.DateOffset(months=12)
        if d1 > last:
            continue
        p0, p1 = spx_m.asof(d0), spx_m.asof(d1)
        if p0 and p1 and not pd.isna(p0) and not pd.isna(p1):
            b = _bucket_of(v)
            if b:
                data[b].append((p1 / p0 - 1) * 100)
    return [{"bucket": lbl, "avg": (sum(data[lbl]) / len(data[lbl]) if data[lbl] else None),
             "n": len(data[lbl])} for _, _, lbl in COMP_BUCKETS]


def probabilities(loaded=None, start="1999-01-01") -> dict:
    """Empirical base rates conditioned on the CURRENT composite bucket. Honest, small-sample."""
    loaded = indicators.load_all() if loaded is None else loaded
    comp = composite_series(loaded, start)
    cur_comp = [v for _, v in comp if v is not None][-1]
    cur_bucket = _bucket_of(cur_comp)
    spx = fetch_market.history("^GSPC")
    spx_m = spx.resample("ME").last() if spx is not None else None
    hy = _series_by_name(loaded, "High-yield OAS")
    nber = [pd.Timestamp(x) for x in NBER_STARTS]
    rec = dd = cred = n = 0
    for d, v in comp:
        if v is None or _bucket_of(v) != cur_bucket:
            continue
        d0 = pd.Timestamp(d); d1 = d0 + pd.DateOffset(months=12)
        if spx_m is not None and d1 > spx_m.index.max():
            continue
        n += 1
        if any(d0 < s <= d1 for s in nber):
            rec += 1
        if spx_m is not None:
            window = spx_m[(spx_m.index > d0) & (spx_m.index <= d1)]
            p0 = spx_m.asof(d0)
            if len(window) and p0 and window.min() / p0 - 1 <= -0.20:
                dd += 1
        if hy is not None:
            hw = hy[(hy.index > d0) & (hy.index <= d1)]
            if len(hw) and hw.max() >= 5.0:
                cred += 1
    pct = lambda x: round(x / n * 100) if n else None
    soft = round((1 - rec / n) * 100) if n else None  # no recession start in next 12m
    return {"bucket": cur_bucket, "n": n, "recession": pct(rec), "drawdown20": pct(dd),
            "credit_proxy": pct(cred), "soft_landing": soft}


def _cosine(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def analogs(loaded=None, top=5) -> list:
    """Months whose stress vector most resembles today (cosine sim), best month per year."""
    df = stress_matrix(loaded)
    # drop short-history columns (e.g. credit spreads with only a few yrs) BEFORE dropping
    # rows, or one short series voids the entire historical matrix.
    good = df.columns[df.notna().mean() >= 0.8]
    df = df[good].dropna(how="any")
    if len(df) < 13:
        return []
    cur = df.iloc[-1].values
    cutoff = df.index[-24] if len(df) > 24 else df.index[-6]  # exclude recent 2y -> surface true historical analogs
    best = {}
    for idx, row in df.iloc[:-1].iterrows():
        if idx >= cutoff:
            continue
        sim = _cosine(cur, row.values)
        y = idx.year
        if y not in best or sim > best[y][1]:
            best[y] = (idx, sim)
    ranked = sorted(best.values(), key=lambda t: -t[1])[:top]
    return [{"date": d.isoformat(), "year": d.year, "sim": round(s * 100)} for d, s in ranked]


def regime(rows, c, tr) -> str:
    by = {r["name"]: r for r in rows}
    comp, breadth = c["composite"], c["breadth"]
    sahm = by.get("Sahm Rule"); claims = by.get("Initial jobless claims")
    val = c["bucket"].get("valuation") or 0; macro = c["bucket"].get("macro_stress") or 0
    if (sahm and sahm["current"] is not None and sahm["current"] >= 0.5) or \
       (claims and claims["ok"] and claims["score"] >= 85):
        return "Recession"
    if comp >= BANDS["warning"] and breadth >= 0.5:
        return "Late-cycle / pre-recession"
    if val >= 85 and macro < 55:
        return "Bubble / late-cycle"
    if (tr.get("d3") or 0) < -4 and comp < BANDS["watch"]:
        return "Recovery"
    if comp < BANDS["benign"]:
        return "Expansion"
    return "Late-cycle"


# scenario presets: absolute stress overrides for named indicators -> recompute composite
SCENARIOS = {
    "AI Boom Continues": {"Shiller CAPE": 100, "Buffett Indicator": 100, "Margin debt YoY%": 90,
                          "VIX": 15, "High-yield OAS": 5, "AAII bull-bear spread": 80},
    "Mild Recession": {"Sahm Rule": 80, "Initial jobless claims": 80, "High-yield OAS": 55,
                       "VIX": 70, "IG credit spread": 50, "U.Mich sentiment": 100},
    "Credit Crisis": {"High-yield OAS": 100, "IG credit spread": 95, "VIX": 95,
                      "Bank lending standards": 90, "Initial jobless claims": 75, "AI-infra credit spread": 95},
    "Inflation Resurgence": {"Core CPI (YoY calc)": 95, "WTI crude": 90, "3M-10Y spread": 30,
                             "2s10s spread": 30, "U.Mich sentiment": 95},
}


def scenario_results(rows, baseline) -> list:
    out = [{"name": "Current", "composite": baseline["composite"], "confidence": baseline["confidence"]}]
    for name, ov in SCENARIOS.items():
        mod = []
        for r in rows:
            r2 = dict(r)
            if r["name"] in ov:
                r2["score"] = float(ov[r["name"]]); r2["ok"] = True
            mod.append(r2)
        cc = scoring.composite(mod)
        out.append({"name": name, "composite": cc["composite"], "confidence": cc["confidence"]})
    return out


# assigned (not measured) confidence by data source — flagged as such on the dashboard
SRC_CONF = {"valuation": 90, "macro": 85, "credit": 90, "labor": 88, "liquidity": 80,
            "sentiment": 70, "other": 70}


def confidence_decomposition(rows) -> list:
    groups = {}
    for r in rows:
        if not r["ok"]:
            continue
        key = "AI / manual" if r["source"] == "manual" else family_of(r["name"])
        conf = 50 if r["source"] == "manual" else SRC_CONF.get(family_of(r["name"]), 70)
        groups.setdefault(key, {"conf": conf, "n": 0})
        groups[key]["n"] += 1
    return sorted(({"source": k, "confidence": v["conf"], "n": v["n"]} for k, v in groups.items()),
                  key=lambda x: x["confidence"])


if __name__ == "__main__":
    loaded = indicators.load_all()
    rows = indicators.compute(loaded)
    c = scoring.composite(rows)
    tr = scoring.trend(loaded)
    print("fwd returns:", forward_returns(loaded))
    print("probabilities:", probabilities(loaded))
    print("analogs:", analogs(loaded))
    print("regime:", regime(rows, c, tr))
    print("scenarios:", [(s["name"], s["composite"]) for s in scenario_results(rows, c)])
    print("confidence:", confidence_decomposition(rows))
