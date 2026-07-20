"""Static HTML report for the cross-asset regime study (separate from output/dashboard.py
-- different cadence: annual/100yr historical study, not the live daily dashboard).

3 correlation heatmaps (full/recession/expansion), a recession-shaded growth-of-100
trajectory chart, the regime playbook table, and the current diagnostic snapshot.
Server-rendered SVG (no client JS needed for a static report); palette follows the
dataviz skill's diverging blue<->red pair (validated in Phase 0 for the categorical
set; the diverging pair here is the documented default, not re-derived).

Run:  py output/regime_study_report.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from config import ROOT
from data import fetch_commodities_long as fcl
from model import regime_study as rs

OUT = os.path.join(ROOT, "output", "regime_study.html")

# dataviz skill reference palette (see references/palette.md)
BLUE, RED, GRAY_L, GRAY_D = "#2a78d6", "#e34948", "#f0efec", "#383835"


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _corr_color(v: float) -> str:
    """diverging blue (+1) <-> gray (0) <-> red (-1)."""
    gray = _hex_to_rgb(GRAY_L)
    if pd.isna(v):
        return GRAY_L
    if v >= 0:
        rgb = _lerp(gray, _hex_to_rgb(BLUE), min(v, 1.0))
    else:
        rgb = _lerp(gray, _hex_to_rgb(RED), min(-v, 1.0))
    return "#%02x%02x%02x" % rgb


def _heatmap_svg(title: str, m: pd.DataFrame, n_note: str) -> str:
    labels = [c.replace(" (S&P 500 TR)", "").replace(" (derived)", "").replace(" (PPI index)", "")
              .replace(" (WTI-era)", "") for c in m.columns]
    n = len(labels)
    cell = 78
    left = 92
    top = 40
    w = left + cell * n + 16
    h = top + cell * n + 46
    svg = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">']
    for j, lbl in enumerate(labels):
        x = left + j * cell + cell / 2
        svg.append(f'<text x="{x}" y="{top - 10}" text-anchor="middle" '
                    f'class="hm-axis" transform="rotate(-20 {x} {top - 10})">{lbl}</text>')
    for i, lbl in enumerate(labels):
        y = top + i * cell + cell / 2 + 4
        svg.append(f'<text x="{left - 8}" y="{y}" text-anchor="end" class="hm-axis">{lbl}</text>')
        for j in range(n):
            v = m.iloc[i, j]
            x, yy = left + j * cell, top + i * cell
            color = _corr_color(v)
            txt = "" if pd.isna(v) else f"{v:+.2f}"
            svg.append(f'<rect x="{x}" y="{yy}" width="{cell - 2}" height="{cell - 2}" '
                        f'rx="4" fill="{color}"/>')
            svg.append(f'<text x="{x + cell / 2 - 1}" y="{yy + cell / 2 + 5}" '
                        f'text-anchor="middle" class="hm-val">{txt}</text>')
    svg.append("</svg>")
    return (f'<div class="card"><h2>{title}</h2><p class="note">{n_note}</p>'
            + "".join(svg) + "</div>")


def _playbook_table(pb: pd.DataFrame) -> str:
    rows = ""
    for regime_name in ["recession", "expansion"]:
        sub = pb[pb["regime"] == regime_name].sort_values("rank")
        rows += f'<tr class="regime-row"><td colspan="5">{regime_name.upper()}</td></tr>'
        for _, r in sub.iterrows():
            rows += (f"<tr><td>{r['asset']}</td><td>{r['avg_return']:+.1%}</td>"
                      f"<td>{r['volatility']:.1%}</td><td>{int(r['n_years'])}</td>"
                      f"<td>#{int(r['rank'])}</td></tr>")
    return (f'<div class="card"><h2>Regime playbook</h2>'
            f'<p class="note">Average annual return &amp; volatility per asset, split by NBER regime. '
            f'Rank 1 = best average return within that regime.</p>'
            f'<table><thead><tr><th>Asset</th><th>Avg return</th><th>Volatility</th>'
            f'<th>Years</th><th>Rank</th></tr></thead><tbody>{rows}</tbody></table></div>')


def _diagnostics_card(snap: pd.DataFrame) -> str:
    rows = ""
    for _, r in snap.iterrows():
        z = r["zscore_vs_history"]
        flag = "extreme" if abs(z) >= 2 else ("elevated" if abs(z) >= 1 else "normal")
        rows += (f'<div class="diag-row"><div class="diag-name">{r["ratio"]}'
                  f'<span class="diag-note">{r["note"]}</span></div>'
                  f'<div class="diag-vals"><span class="diag-latest">{r["latest_value"]:.2f}'
                  f' <span class="diag-yr">({r["latest_year"]})</span></span>'
                  f'<span class="diag-z diag-{flag}">z={z:+.2f}</span></div></div>')
    return (f'<div class="card"><h2>Current diagnostic snapshot</h2>'
            f'<p class="note">Latest reading vs full-sample history (z-score, full-sample mode). '
            f'|z|&ge;2 = extreme, |z|&ge;1 = elevated.</p>{rows}</div>')


def _trajectory_svg(returns: pd.DataFrame, tagged: pd.DataFrame) -> str:
    """Growth-of-100 index per asset (built from the same annual returns used for the
    correlation study), with NBER recession years shaded."""
    W, H, ML, MR, MT, MB = 900, 340, 54, 16, 12, 28
    plotW, plotH = W - ML - MR, H - MT - MB
    idx = {}
    for col in returns.columns:
        s = returns[col].dropna()
        level, out = 100.0, {}
        for y, r in s.items():
            level *= (1 + r)
            out[y.year] = level
        idx[col] = out
    years_all = sorted({y for d in idx.values() for y in d})
    y0, y1 = years_all[0], years_all[-1]
    vals = [v for d in idx.values() for v in d.values() if v > 0]
    import math
    logmin, logmax = math.log10(min(vals) * 0.9), math.log10(max(vals) * 1.1)

    def xs(yr):
        return ML + (yr - y0) / (y1 - y0) * plotW

    def ys(v):
        return MT + plotH - (math.log10(v) - logmin) / (logmax - logmin) * plotH

    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px">']
    rec_years = sorted(tagged.index[tagged["regime"] == "recession"].year.unique())
    for ry in rec_years:
        svg.append(f'<rect x="{xs(ry):.1f}" y="{MT}" width="{max(xs(ry+1)-xs(ry),2):.1f}" '
                    f'height="{plotH}" class="rec-band"/>')
    colors = [BLUE, "#eda100", "#1baf7a", "#eb6834", "#4a3aa7"]
    for i, (name, d) in enumerate(idx.items()):
        pts = sorted(d.items())
        path = " ".join(f'{"M" if k == 0 else "L"} {xs(y):.1f} {ys(v):.1f}'
                         for k, (y, v) in enumerate(pts))
        svg.append(f'<path d="{path}" fill="none" stroke="{colors[i % 5]}" stroke-width="2"/>')
    svg.append("</svg>")
    legend = "".join(f'<span class="legend-item"><span class="swatch" '
                      f'style="background:{colors[i % 5]}"></span>{name}</span>'
                      for i, name in enumerate(idx.keys()))
    return (f'<div class="card"><h2>Growth of 100 (annual, log scale), recession-shaded</h2>'
            f'<p class="note">Gray bands = NBER recession years. Same 5 assets as the '
            f'correlation study.</p><div class="legend">{legend}</div>' + "".join(svg) + "</div>")


CSS = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--page:#f9f9f7;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#898781;--grid:#e1e0d9;--border:rgba(11,11,11,.10);
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text-primary);background:var(--page)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{
color-scheme:dark;--surface-1:#1a1a19;--page:#0d0d0d;--text-primary:#fff;--text-secondary:#c3c2b7;
--text-muted:#898781;--grid:#2c2c2a;--border:rgba(255,255,255,.10)}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-1:#1a1a19;--page:#0d0d0d;
--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#898781;--grid:#2c2c2a;--border:rgba(255,255,255,.10)}
.viz-root{max-width:980px;margin:0 auto;padding:24px 16px 40px}
*{box-sizing:border-box}
h1{font-size:1.35rem;margin:0 0 4px}
.sub{color:var(--text-secondary);font-size:.9rem;margin:0 0 24px;line-height:1.5}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;
padding:16px 16px 14px;margin-bottom:20px;overflow-x:auto}
.card h2{font-size:1rem;margin:0 0 2px}
.note{color:var(--text-muted);font-size:.78rem;margin:0 0 10px}
.hm-axis{fill:var(--text-muted);font-size:11px}
.hm-val{fill:var(--text-primary);font-size:12px;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:.82rem}
th,td{text-align:right;padding:5px 10px;border-bottom:1px solid var(--grid);
font-variant-numeric:tabular-nums;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--text-muted);font-weight:600}
.regime-row td{background:var(--page);color:var(--text-muted);font-weight:600;
font-size:.72rem;letter-spacing:.04em;text-align:left}
.diag-row{display:flex;justify-content:space-between;align-items:center;gap:12px;
padding:8px 0;border-bottom:1px solid var(--grid)}
.diag-row:last-child{border-bottom:none}
.diag-name{font-size:.85rem}
.diag-note{display:block;color:var(--text-muted);font-size:.72rem;margin-top:2px}
.diag-vals{display:flex;align-items:baseline;gap:10px;white-space:nowrap}
.diag-latest{font-variant-numeric:tabular-nums;font-size:.9rem}
.diag-yr{color:var(--text-muted);font-size:.72rem}
.diag-z{font-size:.72rem;padding:2px 8px;border-radius:10px;font-variant-numeric:tabular-nums}
.diag-normal{background:var(--grid);color:var(--text-secondary)}
.diag-elevated{background:#eda10033;color:#a86a00}
.diag-extreme{background:#e3494833;color:#b23030}
.rec-band{fill:var(--grid);opacity:.6}
.legend{display:flex;flex-wrap:wrap;gap:10px 16px;margin:6px 0 10px;font-size:.76rem}
.legend-item{display:flex;align-items:center;gap:6px;color:var(--text-secondary)}
.swatch{width:12px;height:3px;border-radius:2px}
footer{color:var(--text-muted);font-size:.75rem;line-height:1.6;margin-top:8px}
"""


def build_html() -> str:
    returns = rs.build_returns()
    tagged = rs.attach_regime(returns)
    corrs = rs.correlation_matrices(tagged)
    playbook = rs.regime_playbook(tagged)
    snap = rs.diagnostic_snapshot()

    parts = [
        f"<title>Cross-Asset Regime Study</title><style>{CSS}</style>",
        '<div class="viz-root">',
        "<h1>Cross-Asset Regime Study — Equities vs Commodities</h1>",
        '<p class="sub">Annual returns, 1928/1927/1953/1949-2025 (coverage varies by asset '
        '&mdash; see note below), tagged by NBER recession/expansion (FRED USREC). '
        "Correlation matrices use pairwise-complete years per pair, so sample size differs "
        "per cell (see the yellow star note under each). Companion to the "
        '<a href="dashboard.html">live dashboard</a> and the standalone '
        '<a href="https://claude.ai/code/artifact/607d6807-6ffa-449a-9e3c-f001a14fb3d8" '
        'target="_blank" rel="noopener">100yr asset-class chart</a>.</p>',
        _trajectory_svg(returns, tagged),
        _heatmap_svg("Full-period correlation", corrs["full_period"],
                     "All years, 1928-2025 where each asset has data (pairwise-complete)."),
        _heatmap_svg("Recession-only correlation", corrs["recession"],
                     "NBER recession years only -- small sample (8-16 years per pair); "
                     "read as a signal, not a precise estimate."),
        _heatmap_svg("Expansion-only correlation", corrs["expansion"],
                     "NBER expansion years only."),
        _playbook_table(playbook),
        _diagnostics_card(snap),
        "<footer>Nominal, not inflation-adjusted. Silver is derived (NY gold price / "
        "MeasuringWorth gold-silver ratio) -- USGS Data Series 140 and Macrotrends both "
        "block automated fetches (WAF/Cloudflare challenge). Copper is a PPI index "
        "(FRED WPU102502, Dec 1953-), not a $/lb spot price. Pre-1934 gold (and pre-1968 "
        "silver) reflects government-fixed prices, not a freely traded market. Oil begins "
        "1949 (EIA first continuous series). Equities-vs-commodity correlations, "
        "especially recession-only, are informative but statistically noisy given "
        "8-16 recession-year samples for the shorter series.</footer>",
        "</div>",
    ]
    return "\n".join(parts)


def main():
    html = build_html()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", OUT, f"({len(html)} bytes)")


if __name__ == "__main__":
    main()
