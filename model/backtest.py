"""Validate the composite against history BEFORE trusting any live verdict.

Sweeps the model month-by-month from 1997-2021 using strictly point-in-time data
(no lookahead), then checks three questions the brief insists on:
  1. Did the composite rise ahead of the 2000 top and the 2007 top?  (sensitivity)
  2. Did it correctly STAY LOW before COVID, an exogenous shock?       (no false genius)
  3. How often does it fire in benign months?                          (false-positive rate)

A model that screams for years and is right once is a doom mirror, not a signal.
The calibration table is the defense against that.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import CFG
from model import indicators, scoring

# Equity peaks (the moment the thesis would have needed to fire BEFORE)
PEAKS = {"Dot-com 2000": "2000-03-24", "GFC 2007": "2007-10-09", "COVID 2020": "2020-02-19"}
# NBER recession ends — used to bound each "crisis window" for false-positive accounting
REC_END = {"Dot-com 2000": "2001-11-30", "GFC 2007": "2009-06-30", "COVID 2020": "2020-04-30"}
# Corrections that were NOT recessions — the model should NOT sustain a high signal here
NON_EVENTS = {"2011 debt-ceiling": "2011", "2015-16 China/oil": "2015", "2018-Q4 scare": "2018"}


def _mdiff(a, b):  # whole months from b to a
    return (a.year - b.year) * 12 + (a.month - b.month)


def run():
    print("=" * 74)
    print("  BACKTEST  -  point-in-time composite, monthly 1997-2021 (no lookahead)")
    print("=" * 74)

    loaded = indicators.load_all()
    dates = pd.date_range("1997-01-01", "2021-06-01", freq="MS")
    sweep = {d: scoring.composite_asof(loaded, d) for d in dates}

    def comp_at(month):
        return sweep.get(month, {}).get("composite")

    # ---- per-crisis trajectory ----
    for label, pk in PEAKS.items():
        peak = pd.Timestamp(pk).to_period("M").to_timestamp()
        print(f"\n  {label}   (equity peak {pk})")
        print("   months-before-peak:   T-18    T-12     T-6     T-3     T-0(peak)")
        vals = []
        for lead in (18, 12, 6, 3, 0):
            m = (peak.to_period("M") - lead).to_timestamp()
            c = comp_at(m)
            vals.append(f"{c:5.1f}" if c is not None else "  -- ")
        print("   composite stress:    " + "   ".join(vals))
        window = [d for d in dates if 0 <= _mdiff(peak, d) <= 24]
        mx = max((sweep[d]["composite"] for d in window if sweep[d]["composite"] is not None), default=None)
        print(f"   max composite in 24m pre-peak: {mx:.1f}" if mx is not None else "   (insufficient history)")

    # ---- calibration: lead time vs false-positive rate at candidate thresholds ----
    crisis_windows = []
    for label, pk in PEAKS.items():
        start = (pd.Timestamp(pk).to_period("M") - 12).to_timestamp()
        crisis_windows.append((start, pd.Timestamp(REC_END[label])))
    benign = [d for d in dates if not any(s <= d <= e for s, e in crisis_windows)]

    print("\n  " + "-" * 70)
    print("  CALIBRATION - lead time to each peak vs benign-month false-positive rate")
    print(f"  (benign = the {len(benign)} sweep months outside any [peak-12m .. recession-end])")
    print("  " + "-" * 70)
    print("   thresh |  Dot-com   |   GFC      |  COVID     | benign false-positive")
    for T in (60, 65, 70, 75):
        cells = []
        for label, pk in PEAKS.items():
            peak = pd.Timestamp(pk).to_period("M").to_timestamp()
            pre = sorted([d for d in dates if 0 <= _mdiff(peak, d) <= 18])
            fired = [d for d in pre if (comp_at(d) or 0) >= T]
            if not fired:
                cells.append("  miss   ")
            else:
                cells.append(f"{_mdiff(peak, fired[0]):2d}m lead")
        fp = sum(1 for d in benign if (comp_at(d) or 0) >= T) / len(benign) * 100
        print(f"    >={T:<3d} | {cells[0]:^10s} | {cells[1]:^10s} | {cells[2]:^10s} |  {fp:4.1f}%")

    # ---- non-event over-firing check ----
    print("\n  NON-EVENT YEARS (should NOT show sustained crisis-level composite):")
    for label, yr in NON_EVENTS.items():
        yvals = [sweep[d]["composite"] for d in dates if d.year == int(yr) and sweep[d]["composite"] is not None]
        if yvals:
            print(f"    {label:20s} {yr}: max composite {max(yvals):5.1f}, avg {sum(yvals)/len(yvals):5.1f}")

    print("\n" + "=" * 74)
    print("  Read it honestly: pick the threshold with strong lead AND low benign FP%.")
    print("  COVID SHOULD look weak pre-peak - it was exogenous; predicting it = overfit.")
    print("=" * 74)


if __name__ == "__main__":
    run()
