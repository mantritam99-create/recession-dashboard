"""Orchestrator. MILESTONE 1: data layer + normalization.

Pulls every reachable indicator, normalizes each to a 0-100 percentile stress
score, prints a grouped table, and appends a line to log.md. Scoring/breadth/
verdict/backtest are the next milestones (model/scoring.py, backtest.py, verdict.py).
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CFG, has_fred
from model import indicators, scoring
from output import verdict

BUCKETS = ["valuation", "macro_stress", "sentiment"]


def main():
    print("=" * 72)
    print("  RECESSION / BUBBLE-RISK DASHBOARD  -  Milestone 1: data layer")
    print(f"  {datetime.datetime.now():%Y-%m-%d %H:%M}   FRED key: "
          f"{'present' if has_fred() else 'MISSING (FRED indicators skipped)'}")
    print("=" * 72)

    loaded = indicators.load_all()
    rows = indicators.compute(loaded)
    ok = [r for r in rows if r["ok"]]

    for b in BUCKETS:
        brows = [r for r in rows if r["bucket"] == b]
        bok = [r for r in brows if r["ok"]]
        avg = sum(r["score"] for r in bok) / len(bok) if bok else None
        head = f"  {b.upper():14s}  bucket stress: " + (f"{avg:5.1f}" if avg is not None else " n/a ")
        print("\n" + head + f"   ({len(bok)}/{len(brows)} indicators live)")
        print("  " + "-" * 68)
        for r in sorted(brows, key=lambda x: (x["score"] is None, -(x["score"] or 0))):
            cur = f"{r['current']:.2f}" if r["current"] is not None else "n/a"
            sc = f"{r['score']:5.1f}" if r["ok"] else "  -- (no data)"
            flag = " <DANGER" if r["ok"] and r["score"] >= CFG["breadth"]["danger_zone"] else ""
            print(f"    {r['name']:26s} cur={cur:>10s}  stress={sc}{flag}")

    danger = [r for r in ok if r["score"] >= CFG["breadth"]["danger_zone"]]
    c = scoring.composite(rows)

    print("\n" + "=" * 72)
    print("  COMPOSITE  (weighted, breadth-adjusted)")
    print("  " + "-" * 68)
    bk = c["bucket"]; wu = c["weights_used"]
    for b in ["valuation", "macro_stress", "sentiment"]:
        v = bk[b]
        w = wu.get(b)
        wtxt = f"w={w:.2f}" if w is not None else "w=  -- (no data)"
        print(f"    {b:14s} {('%5.1f' % v) if v is not None else '  -- '}   {wtxt}")
    miss = f"  (renormalized; missing: {', '.join(c['missing_buckets'])})" if c["missing_buckets"] else ""
    print("  " + "-" * 68)
    print(f"    COMPOSITE STRESS : {c['composite']:.1f}{miss}")
    print(f"    BREADTH          : {c['breadth']:.2f}  ({len(danger)}/{len(ok)} live indicators in danger zone)")
    print(f"    THESIS CONFIDENCE: {c['confidence']:.1f} +/- {c['margin']:.0f}   "
          f"(data coverage {c['coverage']*100:.0f}%)")
    t = scoring.trend(loaded)
    if t["d3"] is not None:
        arrow = "rising" if t["d3"] > 1 else ("falling" if t["d3"] < -1 else "flat")
        print(f"    MOMENTUM (core)  : {t['now']:.1f} now vs {t['m3']:.1f} 3m ago "
              f"(delta {t['d3']:+.1f}, {arrow})")
    if c["stale"]:
        print(f"    NOTE: stale manual inputs: {', '.join(c['stale'])}")
    print("=" * 72)

    print()
    print(verdict.render(rows, c))

    _log(rows, ok, danger, c)


def _log(rows, ok, danger, c):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.md")
    top = sorted(ok, key=lambda r: -r["score"])[:3]
    line = (f"\n### {datetime.datetime.now():%Y-%m-%d %H:%M}\n"
            f"- composite **{c['composite']}** | confidence **{c['confidence']} +/-{c['margin']:.0f}** "
            f"| breadth {c['breadth']}\n"
            f"- buckets val/macro/sent: {c['bucket']['valuation']} / "
            f"{c['bucket']['macro_stress']} / {c['bucket']['sentiment']}\n"
            f"- live: {len(ok)}/{len(rows)} | danger-zone: {len(danger)}\n"
            f"- highest stress: " +
            ", ".join(f"{r['name']} ({r['score']:.0f})" for r in top) + "\n")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


if __name__ == "__main__":
    main()
