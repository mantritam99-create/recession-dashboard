"""Self-contained HTML dashboard. No CDN — inline CSS + hand-drawn SVG, works offline.

Built for signal + MOTION, not looks: the composite trajectory, per-indicator
3-month stress deltas, trip-wire proximity, "what's moving most", and the
bull-case-defeaters panel. Reads the same live engine as main.py.
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import CFG, ROOT, has_fred
from model import indicators, scoring
from output import verdict

OUT = os.path.join(ROOT, "output", "dashboard.html")


# ---------- color helpers ----------
def _band_color(comp):
    b = CFG["bands"]["composite"]
    if comp is None: return "#5a6b80"
    if comp < b["benign"]:  return "#36d399"
    if comp < b["watch"]:   return "#9acd32"
    if comp < b["warning"]: return "#ffcd5b"
    if comp < b["acute"]:   return "#ff8c42"
    return "#ff5b5b"

def _stress_color(s):
    if s is None: return "#5a6b80"
    if s < 30: return "#36d399"
    if s < 50: return "#9acd32"
    if s < 70: return "#ffcd5b"
    if s < 85: return "#ff8c42"
    return "#ff5b5b"

def _fmt(v):
    if v is None: return "n/a"
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"

def _arrow(d):
    if d is None: return '<span class="flat">&middot;</span>'
    if d > 1:  return f'<span class="up">&#9650; +{d:.0f}</span>'
    if d < -1: return f'<span class="dn">&#9660; {d:.0f}</span>'
    return f'<span class="flat">&middot; {d:+.0f}</span>'


# ---------- SVG sparkline of the composite trajectory ----------
def _spark(hist, warn=70, w=660, h=150):
    pts = [(i, v) for i, (_, v) in enumerate(hist) if v is not None]
    if len(pts) < 2:
        return "<p class='muted'>insufficient history</p>"
    vals = [v for _, v in pts]
    lo = min(vals + [warn]) - 5
    hi = max(vals + [warn]) + 5
    padx, pady = 36, 14
    iw, ih = w - 2 * padx, h - 2 * pady
    n = len(hist) - 1
    def X(i): return padx + (i / n) * iw
    def Y(v): return pady + (1 - (v - lo) / (hi - lo)) * ih
    poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pts)
    y70 = Y(warn)
    dots = "".join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="2.5" fill="#e7edf5"/>' for i, v in pts)
    last_i, last_v = pts[-1]
    return f'''<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="none">
      <line x1="{padx}" y1="{y70:.1f}" x2="{w-padx}" y2="{y70:.1f}" stroke="#ff8c42"
            stroke-dasharray="5 4" stroke-width="1"/>
      <text x="{w-padx+2}" y="{y70:.1f}" fill="#ff8c42" font-size="10" dy="3">70 warn</text>
      <polyline points="{poly}" fill="none" stroke="#5b9dff" stroke-width="2.5"/>
      {dots}
      <circle cx="{X(last_i):.1f}" cy="{Y(last_v):.1f}" r="4.5" fill="#5b9dff"/>
      <text x="{padx}" y="{h-2}" fill="#8a99ad" font-size="10">{hist[0][0]}</text>
      <text x="{w-padx}" y="{h-2}" fill="#8a99ad" font-size="10" text-anchor="end">{hist[-1][0]}</text>
    </svg>'''


def _proximity(t, val):
    """0..1 fraction toward the trigger (heuristic, for the trip-wire bars)."""
    lvl = t["level"]
    if t["trips_when"] == "above":
        return max(0.0, min(1.0, val / lvl)) if lvl else 0.0
    span = 3.5  # 'below' wires (e.g. curve): scale gap into a sane bar
    return max(0.0, min(1.0, (lvl + span - val) / span))


def build():
    loaded = indicators.load_all()
    rows = indicators.compute(loaded)
    c = scoring.composite(rows)
    a = verdict.assess(rows, c)
    hist = scoring.composite_history(loaded, months=12)
    deltas = scoring.indicator_deltas(loaded, lookback=3)
    tr = scoring.trend(loaded)

    base = pd.Timestamp(datetime.date.today()).to_period("M")
    bnow = scoring.composite_asof(loaded, base.to_timestamp(how="end"))["bucket"]
    bpast = scoring.composite_asof(loaded, (base - 3).to_timestamp(how="end"))["bucket"]

    bc = _band_color(c["composite"])

    # --- buckets ---
    bucket_cards = []
    for b, lbl in [("valuation", "Valuation"), ("macro_stress", "Macro stress"), ("sentiment", "Sentiment")]:
        v = c["bucket"][b]
        d = (bnow.get(b) - bpast.get(b)) if (bnow.get(b) is not None and bpast.get(b) is not None) else None
        w = c["weights_used"].get(b)
        vtxt = f"{v:.1f}" if v is not None else "n/a"
        wtxt = f"{w:.2f}" if w is not None else "--"
        bar = f'<div class="bar"><span style="width:{v or 0:.0f}%;background:{_stress_color(v)}"></span></div>'
        bucket_cards.append(f'''<div class="card bcard">
          <div class="brow"><b>{lbl}</b><span class="muted">w {wtxt}</span></div>
          <div class="bval">{vtxt}</div>
          {bar}<div class="muted small">3m {_arrow(d)}</div></div>''')

    # --- trip-wires ---
    tw_rows = []
    for trip, t, val in a["tripwires"]:
        if val is None:
            dot, bar = '<span class="dot gray"></span>', ''
        else:
            f = _proximity(t, val)
            col = "#ff5b5b" if trip else ("#ff8c42" if f >= 0.75 else "#36d399")
            dot = f'<span class="dot" style="background:{col}"></span>'
            bar = f'<div class="bar tw"><span style="width:{f*100:.0f}%;background:{col}"></span></div>'
        op = "&lt;" if t["trips_when"] == "below" else "&gt;"
        box = "&#9745;" if trip else "&#9744;"
        tw_rows.append(f'''<tr><td>{box} {dot}{t['name']}</td>
          <td class="muted">{op} {_fmt(t['level'])}</td>
          <td>{_fmt(val)}</td><td style="width:130px">{bar}</td>
          <td class="muted small">{t['note']}</td></tr>''')

    # --- defeaters ---
    defs = "".join(f'<li>{r["name"]} <span class="muted">stress {r["score"]:.1f}</span></li>'
                   for r in a["defeaters"]) or "<li>none — even calm indicators are now stressed</li>"

    # --- movers (what's moving most, 3m) ---
    mv = sorted(deltas.items(), key=lambda kv: kv[1])
    fallers = [f'<li><span class="dn">&#9660; {d:.0f}</span> {n}</li>' for n, d in mv[:4] if d < -1]
    risers = [f'<li><span class="up">&#9650; +{d:.0f}</span> {n}</li>' for n, d in reversed(mv) if d > 1][:4]

    # --- indicator table ---
    trows = []
    for r in sorted(rows, key=lambda r: (not r["ok"], -(r["score"] or 0))):
        if not r["ok"]:
            continue
        d = deltas.get(r["name"])
        src = '<span class="tag manual">manual</span>' if r["source"] == "manual" else '<span class="tag">live</span>'
        stale = ' <span class="tag stale">STALE</span>' if r.get("stale") else ''
        sc = r["score"]
        bar = f'<div class="bar"><span style="width:{sc:.0f}%;background:{_stress_color(sc)}"></span></div>'
        trows.append(f'''<tr><td>{r["name"]}{stale}</td><td class="muted">{r["bucket"]}</td>
          <td>{_fmt(r["current"])}</td><td style="width:120px">{bar}</td>
          <td class="num">{sc:.0f}</td><td>{_arrow(d)}</td><td>{src}</td></tr>''')

    stale_note = (f'<div class="warnbar">&#9888; Stale manual inputs widening the interval: '
                  f'{", ".join(c["stale"])}</div>' if c["stale"] else '')
    d3 = tr["d3"]
    trend_txt = (f'{tr["now"]:.1f} now vs {tr["m3"]:.1f} 3m ago '
                 f'({"+" if (d3 or 0) >= 0 else ""}{d3:.1f})' if d3 is not None else 'n/a')

    html = _TEMPLATE.format(
        ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        fred=("FRED live" if has_fred() else "FRED key MISSING"),
        conf=f"{c['confidence']:.0f}", margin=f"{c['margin']:.0f}",
        comp=f"{c['composite']:.0f}", breadth=f"{c['breadth']:.2f}",
        band_color=bc, stance=a["label"], stance_txt=a["stance"],
        coverage=f"{c['coverage']*100:.0f}", n_live=c["n_live"], n_total=c["n_total"],
        spark=_spark(hist), trend_txt=trend_txt, trend_arrow=_arrow(d3),
        buckets="".join(bucket_cards), tripwires="".join(tw_rows),
        tripped=a["tripped"], n_tw=len(a["tripwires"]),
        defeaters=defs, risers="".join(risers) or "<li>none</li>",
        fallers="".join(fallers) or "<li>none</li>",
        table="".join(trows), stale_note=stale_note,
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    return OUT


_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recession / Bubble-Risk Dashboard</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#0b0f17;color:#e7edf5;
 font-family:'Segoe UI',system-ui,sans-serif;padding:20px}}
.wrap{{max-width:1180px;margin:0 auto}}h1{{font-size:20px;margin:0}}
.muted{{color:#8a99ad}}.small{{font-size:11px}}.num{{font-variant-numeric:tabular-nums;text-align:right}}
.sub{{color:#8a99ad;font-size:12px;margin-top:3px}}
.card{{background:#131a26;border:1px solid #243042;border-radius:12px;padding:14px 16px;margin-bottom:14px}}
.hero{{display:grid;grid-template-columns:300px 1fr;gap:14px}}
.gauge{{text-align:center;border-left:6px solid var(--bc)}}
.big{{font-size:60px;font-weight:800;line-height:1;color:var(--bc)}}
.stance{{display:inline-block;margin-top:8px;padding:5px 12px;border-radius:999px;
 font-weight:700;font-size:13px;background:var(--bc);color:#06101f}}
.row{{display:flex;gap:14px}}.row>*{{flex:1}}
.bucketwrap{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
.bcard .brow{{display:flex;justify-content:space-between}}.bval{{font-size:30px;font-weight:700;margin:4px 0}}
.bar{{background:#1a2434;border-radius:6px;height:9px;overflow:hidden;margin:4px 0}}
.bar>span{{display:block;height:100%}}.bar.tw{{height:7px}}
.cols{{display:grid;grid-template-columns:1.4fr 1fr;gap:14px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #1c2636}}
th{{color:#8a99ad;text-transform:uppercase;font-size:10px;letter-spacing:.5px}}
.up{{color:#ff6b6b;font-weight:700}}.dn{{color:#36d399;font-weight:700}}.flat{{color:#8a99ad}}
.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}}
.dot.gray{{background:#5a6b80}}
.tag{{font-size:9.5px;padding:1px 6px;border-radius:5px;background:#1f2c3e;color:#8a99ad}}
.tag.manual{{background:#3a2a4a;color:#c98aff}}.tag.stale{{background:#4a2a2a;color:#ff8c42}}
h3{{font-size:13px;margin:0 0 8px;text-transform:uppercase;letter-spacing:.5px;color:#8a99ad}}
ul{{margin:0;padding-left:4px;list-style:none}}ul li{{padding:3px 0;font-size:13px}}
.warnbar{{background:#3a2a1a;border:1px solid #ff8c42;color:#ffcd5b;padding:8px 12px;border-radius:8px;
 font-size:12px;margin-bottom:14px}}
.legend{{font-size:11px;color:#8a99ad}}footer{{color:#5a6b80;font-size:11px;margin-top:10px;line-height:1.5}}
</style></head><body><div class="wrap">
<div style="display:flex;justify-content:space-between;align-items:baseline">
 <div><h1>Recession / Bubble-Risk Dashboard</h1>
 <div class="sub">{ts} &middot; {fred} &middot; {n_live}/{n_total} indicators &middot; coverage {coverage}%</div></div>
 <div class="legend">stress 0&ndash;100 by historical percentile &middot; &#9650; rising risk &#9660; falling</div>
</div>
{stale_note}
<div class="hero">
 <div class="card gauge" style="--bc:{band_color}">
  <div class="muted small">THESIS CONFIDENCE</div>
  <div class="big">{conf}</div><div class="muted">/ 100 &nbsp; &plusmn; {margin}</div>
  <div class="stance">{stance}</div>
  <div class="sub">{stance_txt}</div>
  <div class="sub" style="margin-top:8px">composite {comp} &middot; breadth {breadth}</div>
 </div>
 <div class="card">
  <h3>Composite trajectory &mdash; 12 months &nbsp; <span style="color:#e7edf5">{trend_arrow}</span>
   <span class="muted" style="text-transform:none;font-weight:400"> {trend_txt}</span></h3>
  {spark}
  <div class="legend">core composite (series only; the manual layer has no history yet). Above the dashed 70 line = backtested warning zone.</div>
 </div>
</div>
<div class="bucketwrap">{buckets}</div>
<div class="cols">
 <div class="card"><h3>What would confirm the crash &middot; {tripped}/{n_tw} tripped</h3>
  <table>{tripwires}</table></div>
 <div class="card"><h3>Bull-case defeaters (against the thesis)</h3><ul>{defeaters}</ul>
  <h3 style="margin-top:14px">Moving most (3m)</h3>
  <div class="row"><div><div class="muted small">RISING RISK</div><ul>{risers}</ul></div>
  <div><div class="muted small">EASING</div><ul>{fallers}</ul></div></div>
 </div>
</div>
<div class="card"><h3>All indicators (sorted by stress)</h3>
 <table><tr><th>Indicator</th><th>Bucket</th><th>Current</th><th>Stress</th><th>0-100</th><th>3m &Delta;</th><th>Src</th></tr>
 {table}</table></div>
<footer>Illustrative/disciplined risk gauge, not a prediction. Stress = historical percentile (live) or calm/stress anchor (manual).
 Bands calibrated by model/backtest.py (>=70 caught the 2000 &amp; 2007 tops, missed exogenous COVID, 7.5% benign false-positive).
 Manual AI-bubble layer is quarterly hand-entered. Use the trip-wire checklist, not valuation alone, as the action signal.</footer>
</div></body></html>"""


if __name__ == "__main__":
    print("wrote", build())
