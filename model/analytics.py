"""Reusable analytics layer for the dashboard components (shared engine).

Everything point-in-time (no lookahead), computed from the same `load_all()` set
so US and a future India build stay in sync. Keep dashboard.py to rendering only.
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import CFG
from model import indicators, scoring

TODAY = datetime.date.today

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


if __name__ == "__main__":
    loaded = indicators.load_all()
    cs = composite_series(loaded)
    vals = [v for _, v in cs if v is not None]
    print(f"trajectory: {len(vals)} pts  {min(vals):.1f}..{max(vals):.1f}  ({cs[0][0]}..{cs[-1][0]})")
    c = scoring.composite(indicators.compute(loaded))
    print("contributions:", contributions(c))
    sp = indicator_sparklines(loaded)
    print("sparklines for", len(sp), "indicators; VIX:", sp.get("VIX"))
