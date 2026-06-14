"""Plain-English verdict + trip-wire checklist + bull-case-defeaters panel.

Translates the composite/confidence into a stance, then does the two things that
keep the tool honest:
  - trip-wires: the specific, watchable lines that would CONFIRM a crash (most
    are currently un-tripped — that's the point; they convert worry into signals)
  - bull-case defeaters: what is actively working AGAINST the thesis right now,
    shown permanently so the dashboard fights the user's own crash bias.
Bands are calibrated by model/backtest.py (see config.yaml `bands`).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CFG
from model import indicators, scoring


def _stance(comp, breadth, tripped, bands):
    if comp < bands["benign"]:
        return "NO CRISIS SIGNAL", "Thesis NOT supported by current data."
    if comp < bands["watch"]:
        return "LATE-CYCLE WATCH", "Early caution; signal building but not elevated."
    if comp < bands["warning"]:
        return "ELEVATED", "Late-cycle risk rising; still below the backtested warning line."
    if comp >= bands["acute"] or tripped >= 3:
        return "ACUTE / BROAD STRESS", "Thesis STRONGLY supported and broad-based."
    if breadth >= 0.5 or tripped >= 2:
        return "ELEVATED RISK - BROADENING", "Thesis SUPPORTED and starting to confirm."
    return "ELEVATED RISK - NOT IMMINENT", "Thesis SUPPORTED, but valuation-driven, not acute stress."


def _tripwires(cur):
    out = []
    for tw in CFG["tripwires"]:
        r = cur.get(tw["indicator"])
        val = r["current"] if r and r["ok"] else None
        if val is None:
            out.append((None, tw, None)); continue
        trip = val <= tw["level"] if tw["trips_when"] == "below" else val >= tw["level"]
        out.append((bool(trip), tw, val))
    return out


def _defeaters(rows):
    calm = [r for r in rows if r["bucket"] == "macro_stress" and r["ok"] and r["score"] < 35]
    return sorted(calm, key=lambda r: r["score"])


def _fmt(v, unit):
    if v is None:
        return "n/a"
    s = f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"
    return s + unit


def assess(rows, c) -> dict:
    """Shared stance/trip-wire/defeater computation, reused by render() and the dashboard."""
    cur = {r["name"]: r for r in rows}
    tw = _tripwires(cur)
    tripped = sum(1 for t, _, _ in tw if t)
    label, stance = _stance(c["composite"], c["breadth"], tripped, CFG["bands"]["composite"])
    return {"label": label, "stance": stance, "tripwires": tw,
            "tripped": tripped, "defeaters": _defeaters(rows)}


def render(rows=None, c=None):
    rows = indicators.compute() if rows is None else rows
    c = scoring.composite(rows) if c is None else c
    bands = CFG["bands"]["composite"]
    a = assess(rows, c)
    tw, tripped, label, stance = a["tripwires"], a["tripped"], a["label"], a["stance"]

    L = ["=" * 74, "  VERDICT", "=" * 74]
    L.append(f"  THESIS CONFIDENCE: {c['confidence']:.0f} / 100  (+/- {c['margin']:.0f})"
             f"     [composite stress {c['composite']:.0f}, breadth {c['breadth']:.2f}]")
    L.append(f"  STANCE: {label}")
    L.append(f"    > {stance}")
    bk = c["bucket"]
    L.append(f"  Buckets:  valuation {bk['valuation']} | macro {bk['macro_stress']} "
             f"| sentiment {bk['sentiment']}    ({c['n_live']}/{c['n_total']} live)")
    L.append(f"  Backtest: >=70 flagged the 2000 top (18m) & 2007 top (8m), missed exogenous")
    L.append(f"            COVID, fired in only 7.5% of benign months. (model/backtest.py)")

    L.append("")
    L.append("  WHAT WOULD CONFIRM THE CRASH   (trip-wires; [X] = tripped):")
    for trip, t, val in tw:
        box = "[X]" if trip else ("[ ]" if trip is not None else "[?]")
        op = "below" if t["trips_when"] == "below" else "above"
        line = (f"    {box} {t['name']:16s} {op} {_fmt(t['level'], t['unit']):>10s}"
                f"   (now {_fmt(val, t['unit']):>10s})   {t['note']}")
        L.append(line)
    L.append(f"    -> {tripped} / {len(tw)} tripped. "
             + ("Acute crash triggers have NOT fired." if tripped == 0
                else "Triggers are starting to fire - watch closely."))

    L.append("")
    L.append("  BULL-CASE DEFEATERS   (working AGAINST the thesis right now):")
    def_ = _defeaters(rows)
    if def_:
        for r in def_:
            L.append(f"    - {r['name']:24s} stress {r['score']:4.1f}   (calm / supportive)")
    else:
        L.append("    - none: even the historically-calm indicators are now stressed.")

    L.append("")
    L.append("  INTERPRETATION:")
    L.append("    " + _interpretation(c, tripped, len(tw), bands))
    L.append("=" * 74)
    return "\n".join(L)


def _interpretation(c, tripped, n_tw, bands):
    comp, breadth = c["composite"], c["breadth"]
    if comp < bands["watch"]:
        return ("No crisis signal. Current data does not support the bearish thesis; "
                "the highest-stress readings are isolated, not broad.")
    if comp < bands["warning"]:
        return ("Late-cycle caution. Risk is building but sits below the backtested warning "
                "line (70). Watch the trip-wires; no defensive action forced yet.")
    if tripped >= 2 or breadth >= 0.5:
        return ("Risk is ELEVATED and BROADENING. Acute triggers are firing and/or breadth is "
                "high - this resembles the months approaching the 2000 and 2007 tops. "
                "Reduce risk deliberately rather than waiting for confirmation.")
    return ("Overvaluation is extreme and undeniable (composite is in the >=70 zone that flagged "
            f"the 2000 & 2007 tops), BUT the acute macro/credit triggers are dormant ({tripped}/{n_tw} "
            f"trip-wires) and breadth is low ({breadth:.2f}). Historically this 'expensive + calm' "
            "setup persisted 12-24 months before resolving. Position defensively; treat the "
            "trip-wire checklist - not the valuation alone - as your action signal.")


if __name__ == "__main__":
    print(render())
