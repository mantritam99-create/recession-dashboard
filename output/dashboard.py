"""Self-contained HTML dashboard (no CDN, inline SVG). Dense, dark, terminal-adjacent.

Checkpoint 1 components: freshness/data-quality header, hero + threshold ladder
(anchored to the REAL ~50-81 operating range, not 0-100), Valuation != Recession
block, distance-to-trip gauges, 20yr composite trajectory with recession bands +
threshold lines, contribution waterfall, bull-case defeaters, movers, and an
evidence table with inline sparklines, family tags, and 3m deltas.
Semantic color only: green=resilience/cushion, amber=watch, red=triggered, blue=reference.
"""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import CFG, ROOT, has_fred
from model import indicators, scoring, analytics
from output import verdict

OUT = os.path.join(ROOT, "output", "dashboard.html")
BANDS = CFG["bands"]["composite"]   # benign55 watch65 warning70 acute80

GLOSSARY = {
    "Shiller CAPE": "Cyclically-adjusted P/E: price / 10yr average inflation-adjusted earnings.",
    "Buffett Indicator": "Total US equity market cap / GDP. >100% = richly valued.",
    "High-yield OAS": "Junk-bond option-adjusted spread over Treasuries; widening = credit stress.",
    "IG credit spread": "Investment-grade corporate spread over Treasuries.",
    "Sahm Rule": "Recession trigger: 3m-avg unemployment up >=0.5pp over its prior-12m low.",
    "3M-10Y spread": "10yr minus 3m Treasury yield; negative (inverted) precedes recessions.",
    "2s10s spread": "10yr minus 2yr Treasury yield.",
    "VIX": "Implied 30-day S&P volatility ('fear gauge').",
    "Core CPI (YoY calc)": "Consumer inflation ex food & energy, year-over-year.",
    "WTI crude": "US crude oil price; spikes pressure growth.",
    "Initial jobless claims": "Weekly new unemployment filings; rising = labor cracking.",
    "Bank lending standards": "Net % of banks tightening C&I loan standards (SLOOS).",
    "Credit card delinquency": "Share of card balances 90+ days delinquent.",
    "U.Mich sentiment": "University of Michigan consumer sentiment index.",
    "Personal savings rate": "Household savings as % of disposable income.",
    "Margin debt YoY%": "FINRA margin debt growth; high = leverage building.",
    "NVDA inventory days": "NVIDIA inventory / COGS x 90; rising = demand softening.",
    "Hyperscaler capex QoQ%": "Big-tech AI capex growth; a cut is the bubble catalyst.",
    "AI-infra credit spread": "Oracle/CoreWeave bond spreads; AI-buildout financing stress.",
    "AAII bull-bear spread": "Retail bulls minus bears; high = complacency.",
    "Insider buy/sell ratio": "Corporate insider buys vs sells; low = insiders selling.",
}


# ---------- semantic color ----------
def scol(s):
    if s is None: return "var(--muted)"
    if s < 45: return "var(--green)"
    if s < 70: return "var(--amber)"
    return "var(--red)"

def zone_of(comp):
    # locked 4-label ladder (Phase 0c): Normal / Elevated / Warning / Triggered
    if comp < BANDS["benign"]:  return "NORMAL", "var(--green)"
    if comp < BANDS["warning"]: return "ELEVATED", "var(--amber)"
    if comp < BANDS["acute"]:   return "WARNING", "var(--red)"
    return "TRIGGERED", "var(--red)"

def fmt(v):
    if v is None: return "n/a"
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"

def arrow(d):
    if d is None: return '<span class="flat">&middot;</span>'
    if d > 1:  return f'<span class="up">&#9650;{d:.0f}</span>'
    if d < -1: return f'<span class="dn">&#9660;{abs(d):.0f}</span>'
    return f'<span class="flat">&middot;{d:+.0f}</span>'


# ---------- inline SVG: long-run trajectory ----------
def _traj_svg(series, w=900, h=250):
    start = pd.Timestamp(series[0][0])
    def idx(dt):
        dt = pd.Timestamp(dt)
        return (dt.year - start.year) * 12 + (dt.month - start.month) + dt.day / 30.0
    pts = [(i, v) for i, (_, v) in enumerate(series) if v is not None]
    vals = [v for _, v in pts]
    lo, hi = min(vals) - 3, max(vals) + 3
    padL, padR, padT, padB = 34, 10, 10, 20
    iw, ih = w - padL - padR, h - padT - padB
    n = len(series) - 1
    X = lambda i: padL + (i / n) * iw
    Y = lambda v: padT + (1 - (v - lo) / (hi - lo)) * ih
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="none" class="traj">']
    # recession bands
    for s0, s1 in analytics.NBER_RECESSIONS:
        x0, x1 = X(max(0, idx(s0))), X(min(n, idx(s1)))
        out.append(f'<rect x="{x0:.1f}" y="{padT}" width="{max(1,x1-x0):.1f}" height="{ih}" fill="#37506e" opacity="0.28"/>')
    # threshold lines
    for thr, col, lab in [(BANDS["benign"], "var(--green)", "55"), (BANDS["watch"], "var(--amber)", "65"),
                          (BANDS["warning"], "var(--red)", "70 warn")]:
        if lo < thr < hi:
            y = Y(thr)
            out.append(f'<line x1="{padL}" y1="{y:.1f}" x2="{w-padR}" y2="{y:.1f}" stroke="{col}" stroke-dasharray="4 4" stroke-width="1" opacity="0.55"/>')
            out.append(f'<text x="{w-padR}" y="{y-2:.1f}" fill="{col}" font-size="9" text-anchor="end">{lab}</text>')
    # y ticks
    for v in (50, 60, 70, 80):
        if lo < v < hi:
            out.append(f'<text x="2" y="{Y(v)+3:.1f}" fill="var(--muted)" font-size="9">{v}</text>')
    # x year labels
    for yr in range(2000, 2027, 5):
        i = idx(f"{yr}-01-01")
        if 0 <= i <= n:
            out.append(f'<text x="{X(i):.1f}" y="{h-4}" fill="var(--muted)" font-size="9" text-anchor="middle">{yr}</text>')
    # the line
    poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pts)
    out.append(f'<polyline points="{poly}" fill="none" stroke="var(--blue)" stroke-width="1.8"/>')
    li, lv = pts[-1]
    out.append(f'<circle cx="{X(li):.1f}" cy="{Y(lv):.1f}" r="3.5" fill="{zone_of(lv)[1]}"/>')
    out.append("</svg>")
    return "".join(out)


def _spark_svg(vals, w=84, h=20):
    v = [x for x in vals if x is not None]
    if len(v) < 2: return '<span class="muted">&mdash;</span>'
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1
    n = len(vals) - 1
    pts = [(i, x) for i, x in enumerate(vals) if x is not None]
    P = " ".join(f"{(i/n)*w:.1f},{(h-2)-((x-lo)/rng)*(h-4):.1f}" for i, x in pts)
    last = pts[-1][1]
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" class="spark">'
            f'<polyline points="{P}" fill="none" stroke="{scol(last)}" stroke-width="1.4"/></svg>')


# ---------- threshold ladder (anchored to real range) ----------
def _ladder(comp):
    lo, hi = 48.0, 82.0
    segs = [(48, 55, "var(--green)", "benign"), (55, 65, "var(--amber)", "watch"),
            (65, 70, "#e08a2e", "elevated"), (70, 80, "var(--red)", "warning"), (80, 82, "#b5302b", "acute")]
    bar = ""
    for a, b, col, lab in segs:
        wpct = (b - a) / (hi - lo) * 100
        bar += f'<div class="seg" style="width:{wpct:.2f}%;background:{col}" title="{lab}"></div>'
    mk = (comp - lo) / (hi - lo) * 100
    return (f'<div class="ladder"><div class="ladbar">{bar}'
            f'<div class="ladmark" style="left:{mk:.1f}%"></div></div>'
            f'<div class="ladlabels"><span>50</span><span>55</span><span>65</span><span>70</span><span>80</span></div>'
            f'<div class="muted small">score floors ~50 (relative stress index, not 0&ndash;100) &middot; '
            f'&ge;70 = backtested warning zone</div></div>')


def build():
    loaded = indicators.load_all()
    rows = indicators.compute(loaded)
    c = scoring.composite(rows)
    a = verdict.assess(rows, c)
    tr = scoring.trend(loaded)
    deltas = scoring.indicator_deltas(loaded, lookback=3)
    sparks = analytics.indicator_sparklines(loaded)
    fresh = analytics.freshness(rows)
    contrib = analytics.contributions(c)
    traj = analytics.composite_series(loaded)
    by = {r["name"]: r for r in rows}
    # CP2 analytics — each guarded so one failure can't blank the page
    def _safe(fn, default):
        try: return fn()
        except Exception as e: print("  [dashboard] component failed:", e); return default
    regime = _safe(lambda: analytics.regime(rows, c, tr, a["tripped"]), "n/a")
    probs = _safe(lambda: analytics.probabilities(loaded), {})
    fwd = _safe(lambda: analytics.forward_returns(loaded), [])
    anlg = _safe(lambda: analytics.analogs(loaded), [])
    scen = _safe(lambda: analytics.scenario_results(rows, c), [])
    confd = _safe(lambda: analytics.confidence_decomposition(rows), [])

    comp = c["composite"]
    zlab, zcol = zone_of(comp)
    d3 = tr["d3"]
    tripped = a["tripped"]
    tcol = "var(--green)" if tripped == 0 else ("var(--amber)" if tripped < 3 else "var(--red)")
    sowhat = (f'<b>{regime}.</b> Valuation stress is {"extreme" if comp >= 70 else "elevated"}, '
              f'but <b style="color:{tcol}">{tripped}/6</b> recession triggers are armed &mdash; '
              f'the trip-wires are the action signal, not the headline score.')

    P = []
    # ---- data-quality header ----
    vintages = [i["asof"] for i in fresh["items"] if i["asof"]]
    vrange = f'{min(vintages)} &rarr; {max(vintages)}' if vintages else "n/a"
    stale_chip = (f'<span class="chip red">{len(fresh["stale"])} stale</span>'
                  if fresh["stale"] else '<span class="chip green">0 stale</span>')
    P.append(f'''<div class="topbar">
      <div><b>US Recession / Bubble-Risk Monitor</b>
        <span class="muted small">&middot; {datetime.datetime.now():%Y-%m-%d %H:%M} &middot;
        {"FRED live" if has_fred() else "FRED MISSING"}</span></div>
      <div class="qual">
        <span class="chip">{fresh["n_series_live"]} live &middot; {fresh["n_manual"]} manual</span>
        {stale_chip}
        <span class="chip">vintages {vrange}</span>
      </div></div>''')

    # ---- 2a: 4-KPI decision strip (the headline) ----
    P.append(_kpi_strip(regime, comp, zlab, zcol, tripped, tcol, probs, c, d3))

    # ---- so-what banner + ladder + method (context under the KPIs) ----
    P.append(f'''<div class="card">
      <div class="sowhat" style="font-size:13.5px;padding:9px 11px;background:var(--panel2);border-radius:7px;line-height:1.45">{sowhat}</div>
      <div style="margin-top:10px">{_ladder(comp)}</div>
      <div class="interp" style="margin-top:8px">{a["stance"]}</div>
      <details class="method"><summary>How is this built?</summary>
        <div class="muted small">Each indicator scored 0&ndash;100 by its own historical percentile
        (manual AI-layer by calm/stress anchors) &rarr; weighted composite
        ({" / ".join(f'{b.replace("_","-")} {w:.0%}' for b, w in CFG["weights"].items())})
        &rarr; breadth-adjusted into conviction. The AI-bubble layer sits in a separate overlay (not the
        calibrated score). Bands recalibrated on 1997&ndash;2021 by model/backtest.py &mdash; read the regime
        + trip-wires, not the bare number.</div>
      </details>
    </div>''')

    # ---- 2b: Fuel vs Trigger (merged contribution + kindling/spark) | trajectory ----
    P.append(f'''<div class="hero">
      {_fuel_vs_trigger(contrib, comp, by)}
      <div class="card"><h3>Trajectory &middot; 1999&ndash;2026 <span class="muted small">(grey = NBER recessions)</span></h3>
        {_traj_svg(traj)}</div>
    </div>''')

    # ---- Phase 3: regime transition matrix (where next?) under the trajectory ----
    def _trans():
        bs = analytics.bucket_series_monthly(loaded)
        mats = analytics.compute_transition_matrix(bs, horizons=(3, 6))
        return analytics.transition_summary(bs, mats)
    P.append(_safe(lambda: _transition_panel(_trans()), ""))

    # ---- 2c: distance-to-trip gauges, sorted nearest-trigger-first ----
    def _twfill(tw):
        r = by.get(tw["indicator"]); cur = r["current"] if r and r["ok"] else None
        g = analytics.gauge(tw, cur)
        return g["fill"] if g else -1.0
    P.append('<div class="card"><h3>Distance to trip &middot; what would confirm a crash '
             '<span class="muted small">(nearest trigger first)</span></h3><div class="gauges">')
    for tw in sorted(CFG["tripwires"], key=_twfill, reverse=True):
        r = by.get(tw["indicator"])
        cur = r["current"] if r and r["ok"] else None
        P.append(_gauge_html(tw, cur, analytics.gauge(tw, cur)))
    P.append('</div><div class="muted small">green = far from trigger (cushion) &middot; amber = closing in &middot; red = tripped</div></div>')

    # ---- probabilities + forward returns + analogs ----
    P.append(f'<div class="cols3">{_prob_panel(probs)}{_fwd_table(fwd, probs.get("bucket"))}{_analogs(anlg)}</div>')
    # ---- scenario engine + confidence decomposition ----
    P.append(f'<div class="cols2">{_scenarios(scen)}{_confidence(confd)}</div>')

    # ---- defeaters + movers ----
    mv = sorted(deltas.items(), key=lambda kv: kv[1])
    risers = "".join(f'<li>{arrow(d)} {n}</li>' for n, d in reversed(mv) if d > 1)[:600] or "<li class='muted'>none</li>"
    fallers = "".join(f'<li>{arrow(d)} {n}</li>' for n, d in mv if d < -1) or "<li class='muted'>none</li>"
    defs = "".join(f'<li>{r["name"]} <span class="muted">{r["score"]:.0f}</span></li>' for r in a["defeaters"]) \
        or "<li class='muted'>none &mdash; calm indicators now stressed</li>"
    P.append(f'''<div class="cols2">
      <div class="card"><h3>Bull-case defeaters <span class="muted small">(against the thesis)</span></h3><ul class="tight">{defs}</ul></div>
      <div class="card"><h3>Moving most <span class="muted small">(3m stress &Delta;)</span></h3>
        <div class="cols2"><div><div class="muted small">RISING RISK</div><ul class="tight">{risers}</ul></div>
        <div><div class="muted small">EASING</div><ul class="tight">{fallers}</ul></div></div></div>
    </div>''')

    # ---- bubble-history scorecard (Phase 0a) + AI overlay sidecar (Phase 1b) ----
    P.append(_safe(lambda: _history_card(analytics.historical_scorecard(loaded)), ""))
    P.append(_safe(lambda: _ai_overlay(rows), ""))

    # ---- evidence table ----
    P.append(_table(rows, deltas, sparks))

    P.append('<footer>Disciplined risk gauge, not a prediction. Stress = historical percentile (live) or '
             'calm/stress anchor (manual). Bands from model/backtest.py. Use the trip-wire gauges, not valuation alone, '
             'as the action signal. Rebuilt daily via GitHub Actions.</footer>')

    html = (_HEAD + "<style>" + _CSS + "</style></head><body><div class='wrap'>"
            + "".join(P) + "</div>" + _JS + "</body></html>")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    return OUT


def _kpi_strip(regime, comp, zlab, zcol, tripped, tcol, probs, c, d3):
    rec = probs.get("recession") if probs else None
    recv = f"{rec}%" if rec is not None else "n/a"
    reccol = "var(--red)" if (rec or 0) >= 30 else ("var(--amber)" if (rec or 0) >= 15 else "var(--green)")
    dd = d3 or 0
    return f'''<div class="kpis">
      <div class="kpi"><div class="klab">REGIME</div>
        <div class="kval" style="color:{tcol};font-size:19px">{regime}</div>
        <div class="ksub muted small">valuation &times; trigger state</div></div>
      <div class="kpi"><div class="klab">TRIGGERS ARMED</div>
        <div class="kval" style="color:{tcol}">{tripped}<span class="muted" style="font-size:18px">/6</span></div>
        <div class="ksub muted small">the action signal</div></div>
      <div class="kpi"><div class="klab">COMPOSITE</div>
        <div class="kval" style="color:{zcol}">{comp:.0f} <span class="chip" style="border-color:{zcol};color:{zcol};font-size:10px">{zlab}</span></div>
        <div class="ksub muted small">{arrow(d3)} 3m {("+" if dd>=0 else "")}{dd:.1f} &middot; context</div></div>
      <div class="kpi"><div class="klab">12M RECESSION PROB</div>
        <div class="kval" style="color:{reccol}">{recv}</div>
        <div class="ksub muted small">base rate &middot; conviction {c["confidence"]:.0f}&plusmn;{c["margin"]:.0f}, breadth {c["breadth"]:.2f}</div></div>
    </div>'''


def _fuel_vs_trigger(contrib, total, by):
    kindling = ["Shiller CAPE", "Buffett Indicator", "U.Mich sentiment", "Margin debt YoY%", "AAII bull-bear spread"]
    spark = ["3M-10Y spread", "Sahm Rule", "High-yield OAS", "Initial jobless claims", "VIX", "IG credit spread"]
    def chips(names):
        h = ""
        for nm in names:
            r = by.get(nm)
            if not r or not r["ok"]:
                continue
            h += (f'<div class="vrow"><span>{nm}</span>'
                  f'<span class="chip" style="border-color:{scol(r["score"])};color:{scol(r["score"])}">{r["score"]:.0f}</span></div>')
        return h
    return f'''<div class="card">
      <h3>Fuel vs Trigger <span class="muted small">&middot; why the market is vulnerable vs what would ignite it</span></h3>
      {_waterfall(contrib, total)}
      <div class="cols2" style="margin-top:12px">
        <div class="vbox amberbox"><div class="vhead">&#128293; FUEL &mdash; valuation / excess (stretched, can persist)</div>{chips(kindling)}</div>
        <div class="vbox greenbox"><div class="vhead">&#9889; TRIGGER &mdash; credit / labor (the spark, currently quiet)</div>{chips(spark)}</div>
      </div>
      <div class="muted small">Extreme valuation is the fuel; it can stay lit for years. The credit/labor triggers
      are what actually ignite a crash &mdash; treat the trip-wire gauges below, not valuation, as the action signal.</div>
    </div>'''


def _waterfall(contrib, total):
    out = ['<div class="wf">']
    for x in contrib:
        # bar fills to the bucket's STRESS score (0-100 = % of its weight capacity used);
        # the +value is the weighted point-contribution (these sum to the composite).
        out.append(f'''<div class="wfrow"><span class="wflab">{x["bucket"].replace("_"," ")}
          <span class="muted small">w{x["weight"]:.0%}</span></span>
          <div class="wfbar"><span style="width:{x["score"]:.0f}%;background:{scol(x["score"])}"></span></div>
          <span class="wfval">+{x["points"]:.1f}</span></div>''')
    out.append(f'<div class="wfrow tot"><span class="wflab">composite</span>'
               f'<div class="wfbar"><span style="width:{total:.0f}%;background:var(--blue)"></span></div>'
               f'<span class="wfval">{total:.1f}</span></div></div>')
    return "".join(out)


def _transition_panel(ts):
    """Phase 3: from today's regime bucket, the historical Markov stay/ease/worsen split."""
    cur = ts["current"]
    rows = ""
    for k in sorted(ts["horizons"]):
        h = ts["horizons"][k]
        rows += (f'<div class="prow"><span>after <b>{k} months</b></span>'
                 f'<span class="muted small">stay <b>{h["stay"]}%</b> &middot; '
                 f'<span style="color:var(--green)">ease {h["improve"]}%</span> &middot; '
                 f'<span style="color:var(--red)">worsen {h["worsen"]}%</span></span></div>')
    return (f'<div class="card"><h3>Where next? '
            f'<span class="muted small">&middot; historical regime transitions (Markov, 1999&ndash;2026)</span></h3>'
            f'<div class="muted small" style="margin-bottom:6px">From today\'s bucket <b>{cur}</b>, historically:</div>'
            f'{rows}'
            f'<div class="muted small" style="margin-top:6px">Row-normalized, Laplace-smoothed transitions of the '
            f'monthly composite bucket. Stress buckets are episode-dominated (few independent runs) &mdash; '
            f'read as directional, not precise.</div></div>')


def _ai_overlay(rows):
    ai = [r for r in rows if r.get("source") == "manual" and r["bucket"] == "overlay" and r["ok"]]
    if not ai:
        return ""
    items = ""
    for r in sorted(ai, key=lambda r: -(r["score"] or 0)):
        stale = ' <span class="chip red">stale</span>' if r.get("stale") else ''
        items += (f'<div class="vrow"><span>{r["name"]}{stale}<br>'
                  f'<span class="muted small">{GLOSSARY.get(r["name"], "")}</span></span>'
                  f'<span class="chip" style="border-color:{scol(r["score"])};color:{scol(r["score"])}">{r["score"]:.0f}</span></div>')
    return (f'<div class="card"><h3>AI bubble overlay '
            f'<span class="muted small">&middot; thematic sidecar &mdash; NOT in the calibrated composite</span></h3>{items}'
            f'<div class="muted small">Manual quarterly inputs, kept visible because they\'re the current thesis but '
            f'excluded from the backtested score so a stale/bespoke read can\'t move the headline. Note: 3 other manual '
            f'inputs (AAII, insider, margin debt) still sit inside the sentiment bucket.</div></div>')


def _history_card(hist):
    if not hist:
        return ""
    def f(x): return f'{x:.0f}' if x is not None else '&mdash;'
    bnames = list(hist[0]["buckets"].keys())
    thead = "".join(f'<th class="num">{b.replace("_","-").title()}</th>' for b in bnames)
    body = ""
    for h in hist:
        cur = ' class="curbucket"' if h["episode"] == "Current" else ''
        bcells = "".join(f'<td class="num" style="color:{scol(h["buckets"][b])}">{f(h["buckets"][b])}</td>'
                         for b in bnames)
        body += (f'<tr{cur}><td>{h["episode"]}</td><td class="muted small">{h["stage"]}</td>'
                 f'<td class="muted small">{h["date"][:7]}</td>'
                 f'<td class="num"><b>{f(h["composite"])}</b></td>{bcells}'
                 f'<td class="muted num">{h["n_live"]}</td></tr>')
    return (f'<div class="card"><h3>Bubble-history scorecard '
            f'<span class="muted small">&middot; bucket stress at past episodes (full-sample percentile ruler)</span></h3>'
            f'<div class="tblwrap"><table class="mini"><thead><tr>'
            f'<th>Episode</th><th>Stage</th><th>Date</th><th class="num">Composite</th>{thead}'
            f'<th class="num">live n</th></tr></thead><tbody>{body}</tbody></table></div>'
            f'<div class="muted small">Dot-com = valuation-led; GFC = credit/macro-led (valuation even '
            f'collapsed at the Lehman burst as credit/sentiment spiked); today\'s valuation tops the 2000 peak. '
            f'Series-only (manual AI layer excluded). Dates are conventional markers.</div></div>')


def _val_vs_rec(by):
    kindling = ["Shiller CAPE", "Buffett Indicator", "U.Mich sentiment", "Margin debt YoY%", "AAII bull-bear spread"]
    spark = ["3M-10Y spread", "Sahm Rule", "High-yield OAS", "Initial jobless claims", "VIX", "IG credit spread"]
    def chips(names):
        h = ""
        for nm in names:
            r = by.get(nm)
            if not r or not r["ok"]: continue
            h += (f'<div class="vrow"><span>{nm}</span>'
                  f'<span class="chip" style="border-color:{scol(r["score"])};color:{scol(r["score"])}">{r["score"]:.0f}</span></div>')
        return h
    return f'''<div class="card valrec">
      <h3>Valuation risk &ne; Recession risk <span class="muted small">&middot; kindling vs spark</span></h3>
      <div class="cols2">
        <div class="vbox amberbox"><div class="vhead">&#128293; BUBBLE / VALUATION &mdash; the kindling (stretched)</div>{chips(kindling)}</div>
        <div class="vbox greenbox"><div class="vhead">&#9889; RECESSION / CREDIT TRIGGERS &mdash; the spark (absent)</div>{chips(spark)}</div>
      </div>
      <div class="muted small">Extreme valuation is the fuel; it can persist for years. The acute macro/credit
      triggers are what actually ignite a crash &mdash; and they are currently quiet.</div>
    </div>'''


def _gauge_html(tw, cur, g):
    if g is None:
        return f'<div class="gauge"><div class="grow"><b>{tw["name"]}</b><span class="chip">no data</span></div></div>'
    pct = g["fill"] * 100
    col = "var(--red)" if g["tripped"] else ("var(--amber)" if g["fill"] >= 0.66 else "var(--green)")
    state = "TRIPPED" if g["tripped"] else f"{pct:.0f}% to trigger"
    op = "&lt;" if tw["trips_when"] == "below" else "&gt;"
    return f'''<div class="gauge">
      <div class="grow"><b>{tw["name"]}</b><span class="chip" style="border-color:{col};color:{col}">{state}</span></div>
      <div class="gtrack"><span class="gfill" style="width:{pct:.0f}%;background:{col}"></span></div>
      <div class="gfoot muted small">now {fmt(cur)} <span class="sep">|</span> trigger {op} {fmt(tw["level"])}
        <span class="sep">|</span> {tw["note"]}</div>
    </div>'''


def _prob_panel(p):
    if not p or not p.get("n"):
        return '<div class="card"><h3>Probability &middot; next 12m</h3><div class="muted small">insufficient history</div></div>'
    items = [("Recession starts", p["recession"], "red"), ("Drawdown &gt;20%", p["drawdown20"], "red"),
             ("Credit event (HY&gt;5%)", p["credit_proxy"], "amber"), ("Soft landing", p["soft_landing"], "green")]
    def _pf(v):
        if v is None: return "n/a"
        return "&lt;1%" if v == 0 else f"{v}%"
    body = "".join(f'<div class="prow"><span>{lab}</span>'
                   f'<span class="pval {col}">{_pf(v)}</span></div>'
                   for lab, v, col in items)
    return (f'<div class="card"><h3>Probability &middot; next 12m</h3>{body}'
            f'<div class="muted small">empirical base rate when composite in <b>{p["bucket"]}</b> '
            f'(n={p["n"]} mo across <b>{p.get("n_episodes", "?")}</b> independent episodes). '
            f'{p.get("note", "")} Credit/soft-landing are stated proxies, not measured.</div></div>')


def _fwd_table(fwd, cur):
    if not fwd:
        return '<div class="card"><h3>Fwd 12m S&amp;P</h3><div class="muted small">n/a</div></div>'
    body = ""
    for x in fwd:
        hl = ' class="curbucket"' if x["bucket"] == cur else ''
        avg = f'{x["avg"]:+.1f}%' if x["avg"] is not None else "n/a"
        col = "green" if (x["avg"] or 0) > 5 else ("amber" if (x["avg"] or 0) > 0 else "red")
        body += f'<tr{hl}><td>{x["bucket"]}</td><td class="pval {col}">{avg}</td><td class="muted num">{x["n"]}</td></tr>'
    return (f'<div class="card"><h3>Fwd 12m S&amp;P by bucket</h3>'
            f'<table class="mini"><thead><tr><th>Composite</th><th>Avg fwd</th><th>n</th></tr></thead>{body}</table>'
            f'<div class="muted small">historical realized return; current bucket boxed.</div></div>')


ANALOG_TAGS = {
    2000: "dot-com mania peak", 2001: "post-dot-com unwind", 2006: "pre-GFC, credit still calm",
    2007: "pre-GFC credit rollover", 2008: "GFC credit rupture", 2011: "debt-ceiling scare (benign)",
    2015: "China / oil scare (benign)", 2016: "valuation-led, no labor crack", 2018: "Q4 vol scare (benign)",
    2019: "late-cycle, curve inverted", 2021: "valuation-led, no labor crack", 2022: "rate-shock repricing",
    2023: "valuation-led, soft landing", 2024: "valuation-led, no labor crack",
}


def _analogs(a):
    if not a:
        return '<div class="card"><h3>Historical analogs</h3><div class="muted small">n/a</div></div>'
    body = "".join(f'<div class="prow"><span>{x["year"]} '
                   f'<span class="muted small">&middot; {ANALOG_TAGS.get(x["year"], "late-cycle")}</span></span>'
                   f'<span class="pval">{x["sim"]}%</span></div>' for x in a)
    return (f'<div class="card"><h3>Most-similar setups <span class="muted small">(why it matters)</span></h3>{body}'
            f'<div class="muted small">cosine similarity on the stress vector. Note: today\'s closest analogs are '
            f'mostly recent <i>benign</i> years &mdash; which argues against imminence.</div></div>')


def _scenarios(scen):
    if not scen:
        return '<div class="card"><h3>Scenario engine</h3><div class="muted small">n/a</div></div>'
    base = scen[0]["composite"]
    btns = "".join(f'<button class="scbtn" data-i="{i}">{s["name"]}</button>' for i, s in enumerate(scen))
    return (f'<div class="card"><h3>Scenario engine <span class="muted small">(illustrative re-score)</span></h3>'
            f'<div class="scbtns">{btns}</div>'
            f'<div id="scres" class="scres muted small">Tap a scenario to re-score the composite.</div>'
            f'<script>window.__SCEN__={json.dumps(scen)};window.__BASE__={base};</script></div>')


def _confidence(cd):
    if not cd:
        return '<div class="card"><h3>Confidence by source</h3><div class="muted small">n/a</div></div>'
    body = "".join(f'<div class="prow"><span>{x["source"]} <span class="muted small">&times;{x["n"]}</span></span>'
                   f'<span class="pval">{x["confidence"]}%</span></div>' for x in cd)
    return (f'<div class="card"><h3>Confidence by source <span class="muted small">(assigned)</span></h3>{body}'
            f'<div class="muted small">data-quality weights, not statistical CIs &mdash; AI/manual layer lowest. '
            f'<b>Informational only &mdash; not applied to composite math.</b></div></div>')


def _table(rows, deltas, sparks):
    fams = ["all", "valuation", "macro", "credit", "labor", "liquidity", "sentiment"]
    chips = "".join(f'<span class="famchip{" on" if f=="all" else ""}" data-fam="{f}">{f}</span>' for f in fams)
    head = (f'<div class="card"><h3>Evidence &middot; all indicators <span class="muted small">(filter / sort)</span></h3>'
            f'<div class="famfilter">{chips}</div>'
            f'<div class="tblwrap"><table id="evtbl"><thead><tr><th>Indicator</th><th>Family</th><th>Current</th>'
            f'<th data-sort="stress">Stress &#8645;</th><th>18m</th><th data-sort="delta">3m&Delta; &#8645;</th>'
            f'<th>Vintage</th><th>Src</th></tr></thead><tbody>')
    body = ""
    for r in sorted(rows, key=lambda r: (not r["ok"], -(r["score"] or 0))):
        if not r["ok"]: continue
        s = r["score"]; fam = analytics.family_of(r["name"]); d = deltas.get(r["name"])
        sp = _spark_svg(sparks[r["name"]]) if r["name"] in sparks else '<span class="muted">&mdash;</span>'
        src = '<span class="chip manual">man</span>' if r["source"] == "manual" else '<span class="chip">live</span>'
        stale = ' <span class="chip red">stale</span>' if r.get("stale") else ''
        bar = f'<div class="bar"><span style="width:{s:.0f}%;background:{scol(s)}"></span></div>'
        hbg = "rgba(240,84,79,.14)" if s >= 70 else ("rgba(245,181,61,.12)" if s >= 45 else "rgba(47,191,113,.10)")
        tip = GLOSSARY.get(r["name"], "")
        body += (f'<tr data-fam="{fam}" data-stress="{s:.0f}" data-delta="{(d if d is not None else -999):.0f}">'
                 f'<td class="tip" title="{tip}">{r["name"]}{stale}</td>'
                 f'<td><span class="fam">{fam}</span></td><td class="num">{fmt(r["current"])}</td>'
                 f'<td style="background:{hbg}">{bar}<span class="snum">{s:.0f}</span></td><td>{sp}</td><td>{arrow(d)}</td>'
                 f'<td class="muted small">{r.get("asof") or "&mdash;"}</td><td>{src}</td></tr>')
    return head + body + "</tbody></table></div></div>"


_HEAD = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width, initial-scale=1">'
         '<title>US Recession / Bubble-Risk Monitor</title>')

_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0a0e14;color:#dfe7f0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
 font-size:13px;padding:14px}
.wrap{max-width:1180px;margin:0 auto}
:root{--bg:#0a0e14;--panel:#10161f;--panel2:#161f2b;--line:#202d3d;--text:#dfe7f0;--muted:#7d8da0;
 --green:#2fbf71;--amber:#f5b53d;--red:#f0544f;--blue:#5b9dff}
.muted{color:var(--muted)}.small{font-size:11px}.num{text-align:right;font-variant-numeric:tabular-nums}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px;margin-bottom:12px}
h3{font-size:11px;margin:0 0 9px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:700}
.chip{display:inline-block;padding:1px 7px;border:1px solid var(--line);border-radius:6px;font-size:10.5px;
 color:var(--muted);white-space:nowrap}
.chip.green{border-color:var(--green);color:var(--green)}.chip.red{border-color:var(--red);color:var(--red)}
.chip.big{font-size:12px;font-weight:700;padding:3px 10px}.chip.manual{border-color:#9a6cff;color:#b89cff}
.up{color:var(--red);font-weight:700}.dn{color:var(--green);font-weight:700}.flat{color:var(--muted)}
.topbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.qual{display:flex;gap:6px;flex-wrap:wrap}
.hero{display:grid;grid-template-columns:340px 1fr;gap:12px}
.heronum{font-size:62px;font-weight:800;line-height:1;display:flex;align-items:baseline;gap:10px}
.zlab{font-size:12px;font-weight:700;color:#0a0e14;padding:3px 8px;border-radius:6px;align-self:center}
.ladder{margin:10px 0}
.ladbar{position:relative;display:flex;height:14px;border-radius:7px;overflow:hidden}
.seg{height:100%}.ladmark{position:absolute;top:-3px;width:3px;height:20px;background:#fff;border-radius:2px;
 box-shadow:0 0 0 2px #0a0e14}
.ladlabels{display:flex;justify-content:space-between;font-size:9.5px;color:var(--muted);margin-top:3px}
.stancerow{display:flex;align-items:center;gap:8px;margin:10px 0 6px}
.interp{font-size:12px;line-height:1.45}
.method{margin-top:10px}.method summary{cursor:pointer;color:var(--blue);font-size:11px}
.method div{margin-top:6px;line-height:1.5}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
ul.tight{margin:0;padding-left:2px;list-style:none}ul.tight li{padding:2px 0}
/* waterfall */
.wf{display:flex;flex-direction:column;gap:5px}
.wfrow{display:grid;grid-template-columns:92px 1fr 42px;align-items:center;gap:8px;font-size:11.5px}
.wflab{color:var(--muted);text-transform:capitalize}.wfval{text-align:right;font-variant-numeric:tabular-nums}
.wfbar{background:var(--panel2);height:11px;border-radius:5px;overflow:hidden}.wfbar>span{display:block;height:100%}
.wfrow.tot .wflab{color:var(--text);font-weight:700}
/* trajectory */
svg.traj{display:block;background:var(--panel2);border-radius:8px}
/* valuation vs recession */
.valrec .vbox{border-radius:8px;padding:10px;border:1px solid var(--line)}
.amberbox{background:rgba(245,181,61,.06);border-color:rgba(245,181,61,.3)}
.greenbox{background:rgba(47,191,113,.06);border-color:rgba(47,191,113,.3)}
.vhead{font-size:11px;font-weight:700;margin-bottom:8px}
.vrow{display:flex;justify-content:space-between;align-items:center;padding:3px 0;font-size:12px}
/* gauges */
.gauges{display:grid;grid-template-columns:1fr 1fr;gap:11px 18px}
.gauge .grow{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}
.gtrack{background:var(--panel2);height:10px;border-radius:5px;overflow:hidden}
.gfill{display:block;height:100%;border-radius:5px}
.gfoot{margin-top:4px}.sep{opacity:.4;margin:0 4px}
/* table */
.tblwrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px;min-width:640px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid #18222f}
th{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.5px}
.bar{display:inline-block;width:64px;height:8px;background:var(--panel2);border-radius:4px;overflow:hidden;vertical-align:middle}
.bar>span{display:block;height:100%}.snum{margin-left:6px;font-variant-numeric:tabular-nums}
.spark{vertical-align:middle}
.fam{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
footer{color:var(--muted);font-size:10.5px;line-height:1.5;margin-top:8px}
.cols3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.prow{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #18222f;font-size:12px}
.prow:last-child{border-bottom:none}
.pval{font-weight:700;font-variant-numeric:tabular-nums}
.pval.green{color:var(--green)}.pval.amber{color:var(--amber)}.pval.red{color:var(--red)}
table.mini{width:100%;border-collapse:collapse;font-size:12px}
table.mini td,table.mini th{padding:4px 6px;border-bottom:1px solid #18222f;text-align:left}
table.mini th{color:var(--muted);font-size:10px;text-transform:uppercase}
tr.curbucket{background:rgba(91,157,255,.12);outline:1px solid var(--blue)}
.scbtns{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.scbtn{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:7px;padding:5px 9px;font-size:11px;cursor:pointer}
.scbtn:hover{border-color:var(--blue)}.scbtn.on{background:var(--blue);color:#06101f;border-color:var(--blue)}
.scres{padding:8px;background:var(--panel2);border-radius:7px;min-height:18px;font-size:12px}
.famfilter{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:9px}
.famchip{font-size:10.5px;padding:2px 8px;border:1px solid var(--line);border-radius:6px;color:var(--muted);cursor:pointer;text-transform:capitalize}
.famchip:hover{border-color:var(--blue)}.famchip.on{background:var(--blue);color:#06101f;border-color:var(--blue)}
th[data-sort]{cursor:pointer;user-select:none}
.tip{border-bottom:1px dotted #3a4a5e;cursor:help}
/* 4-KPI decision strip */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.klab{font-size:10px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:700;margin-bottom:6px}
.kval{font-size:26px;font-weight:800;line-height:1.1}
.ksub{margin-top:6px}
/* evidence table: frozen first column so the indicator name stays visible when scrolling */
#evtbl td:first-child,#evtbl th:first-child{position:sticky;left:0;background:var(--panel);z-index:1}
@media(max-width:820px){
  .hero,.gauges,.cols2,.cols3{grid-template-columns:1fr}
  .kpis{grid-template-columns:1fr 1fr}
  .heronum{font-size:52px}
}
"""

_JS = """<script>
(function(){  // scenario engine
  var data=window.__SCEN__||[], base=window.__BASE__||0, res=document.getElementById('scres');
  document.querySelectorAll('.scbtn').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('.scbtn').forEach(function(x){x.classList.remove('on');}); b.classList.add('on');
      var s=data[+b.dataset.i]; if(!s){return;} var d=s.composite-base;
      var col=d>0.5?'var(--red)':(d<-0.5?'var(--green)':'var(--muted)');
      res.innerHTML='<b>'+s.name+'</b> &rarr; composite <b style="color:'+col+'">'+s.composite.toFixed(1)+'</b> '
        +'<span style="color:'+col+'">('+(d>=0?'+':'')+d.toFixed(1)+' vs current '+base.toFixed(1)+')</span>'
        +' &middot; conviction '+Math.round(s.confidence);
    });
  });
})();
(function(){  // evidence table: family filter + column sort
  var tbl=document.getElementById('evtbl'); if(!tbl){return;}
  var tb=tbl.querySelector('tbody'), rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));
  document.querySelectorAll('.famchip').forEach(function(ch){
    ch.addEventListener('click',function(){
      document.querySelectorAll('.famchip').forEach(function(x){x.classList.remove('on');}); ch.classList.add('on');
      var f=ch.dataset.fam;
      rows.forEach(function(r){r.style.display=(f==='all'||r.dataset.fam===f)?'':'none';});
    });
  });
  document.querySelectorAll('th[data-sort]').forEach(function(th){
    th.addEventListener('click',function(){
      var k=th.dataset.sort;
      rows.sort(function(a,b){return (parseFloat(b.dataset[k])||-999)-(parseFloat(a.dataset[k])||-999);});
      rows.forEach(function(r){tb.appendChild(r);});
    });
  });
})();
</script>"""

if __name__ == "__main__":
    print("wrote", build())
