"""The AI-bubble + hard-to-automate sentiment layer: manual quarterly inputs.

No clean free API covers hyperscaler capex, NVDA inventory days, AI-infra credit
spreads, AAII/insider/margin-debt — so they're keyed into manual_inputs.csv. Each
row carries `calm` and `stress` anchor values; a single reading maps to a 0-100
stress score by linear interpolation (so we don't need years of history). As you
add a new row each quarter, history accumulates for later percentile scoring.

Stale rows (older than STALE_DAYS) are still used but FLAGGED so the model can
widen its confidence interval rather than silently trusting old data.
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import ROOT

CSV = os.path.join(ROOT, "data", "manual_inputs.csv")
STALE_DAYS = 120  # ~ a quarter; manual layer is quarterly


def _stress(value, calm, stress):
    """Linear map: value at `calm` -> 0, at `stress` -> 100. Handles either direction
    because calm/stress can be ordered low->high or high->low."""
    if stress == calm:
        return None
    frac = (value - calm) / (stress - calm)
    return max(0.0, min(1.0, frac)) * 100.0


def load() -> list[dict]:
    if not os.path.exists(CSV):
        return []
    df = pd.read_csv(CSV, parse_dates=["date"])
    today = pd.Timestamp(datetime.date.today())
    out = []
    for ind, g in df.groupby("indicator"):
        row = g.sort_values("date").iloc[-1]            # newest reading per indicator
        score = _stress(float(row["value"]), float(row["calm"]), float(row["stress"]))
        if score is None:
            continue
        age = (today - row["date"]).days
        out.append({
            "name": row["name"], "bucket": row["bucket"], "value": float(row["value"]),
            "score": round(score, 1), "note": str(row["note"]), "date": row["date"].date(),
            "stale": age > STALE_DAYS, "age_days": age, "source": "manual",
        })
    return out


if __name__ == "__main__":
    for m in load():
        flag = " STALE" if m["stale"] else ""
        print(f"{m['name']:26s} {m['bucket']:13s} val={m['value']:>8.1f}  stress={m['score']:5.1f}"
              f"  ({m['age_days']}d{flag})")
