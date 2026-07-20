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


def _fmt_p(v) -> str:
    if v is None or pd.isna(v):
        return "&mdash;"
    return f"{v:.3f}" if v >= 0.001 else "&lt;0.001"


def _significance_table_html(title: str, df: pd.DataFrame, note: str) -> str:
    """Episode-level (or common-window) pairwise significance: r, 95% CI, p, FDR-adjusted
    q, n_effective, gated. Numbers, not a yes/no tag -- see the legend in build_html()."""
    rows = ""
    for _, r in df.sort_values("gated").iterrows():
        if r["gated"]:
            rows += (f'<tr class="gated-row"><td>{r["asset_a"]} vs {r["asset_b"]}</td>'
                      f'<td colspan="5">insufficient episodes (n={int(r["n_effective"])}) '
                      f'&mdash; descriptive only, no test</td></tr>')
            continue
        sig = r["pearson_p_q"] is not None and pd.notna(r["pearson_p_q"]) and r["pearson_p_q"] < 0.05
        rows += (f'<tr class="{"sig-row" if sig else ""}"><td>{r["asset_a"]} vs {r["asset_b"]}</td>'
                  f'<td>{r["pearson_r"]:+.2f}</td>'
                  f'<td>[{r["pearson_ci_lo"]:+.2f}, {r["pearson_ci_hi"]:+.2f}]</td>'
                  f'<td>{_fmt_p(r["pearson_p"])}</td><td>{_fmt_p(r["pearson_p_q"])}</td>'
                  f'<td>{int(r["n_effective"])}</td></tr>')
    return (f'<div class="card"><h2>{title}</h2><p class="note">{note}</p>'
            f'<table><thead><tr><th>Pair</th><th>Pearson r</th><th>95% CI</th>'
            f'<th>p</th><th>q (FDR)</th><th>n</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def _regime_significance_html(df: pd.DataFrame) -> str:
    rows = ""
    for _, r in df.iterrows():
        if r["gated"]:
            rows += (f'<tr class="gated-row"><td>{r["asset"]}</td>'
                      f'<td colspan="4">insufficient episodes '
                      f'(recession n={int(r["n_recession_episodes"])}, '
                      f'expansion n={int(r["n_expansion_episodes"])}) &mdash; descriptive only</td></tr>')
            continue
        sig = pd.notna(r["mannwhitney_p_q"]) and r["mannwhitney_p_q"] < 0.05
        rows += (f'<tr class="{"sig-row" if sig else ""}"><td>{r["asset"]}</td>'
                  f'<td>{r["recession_mean"]:+.1%}</td><td>{r["expansion_mean"]:+.1%}</td>'
                  f'<td>{_fmt_p(r["welch_p"])} (q={_fmt_p(r["welch_p_q"])})</td>'
                  f'<td>{_fmt_p(r["mannwhitney_p"])} (q={_fmt_p(r["mannwhitney_p_q"])})</td></tr>')
    return (f'<div class="card"><h2>Is the regime difference even real? (episode-level)</h2>'
            f'<p class="note">Per-asset recession-episode vs expansion-episode compounded '
            f'return, Welch\'s t-test and Mann-Whitney U (non-parametric). Values are per-'
            f'episode compounded returns, not annualized -- an expansion episode can span '
            f'many years.</p>'
            f'<table><thead><tr><th>Asset</th><th>Recession mean</th><th>Expansion mean</th>'
            f'<th>Welch p (q)</th><th>Mann-Whitney p (q)</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def _subtype_html(sensitivity: pd.DataFrame) -> str:
    rows = ""
    for _, r in sensitivity.sort_values(["sub_type", "asset"]).iterrows():
        gated = "gated-row" if r["gated"] else ""
        alt = r.get("avg_return_reclassified")
        alt_txt = f"{alt:+.1%}" if pd.notna(alt) else "&mdash;"
        base_txt = f"{r['avg_return_base']:+.1%}" if pd.notna(r["avg_return_base"]) else "&mdash;"
        rows += (f'<tr class="{gated}"><td>{r["sub_type"]}</td><td>{r["asset"]}</td>'
                  f'<td>{int(r["n_effective"])}</td><td>{base_txt}</td><td>{alt_txt}</td></tr>')
    return (f'<div class="card"><h2>Recession sub-types (descriptive only, see '
            f'docs/RECESSION_EPISODES.md)</h2>'
            f'<p class="note">Average per-episode compounded return by recession cause. '
            f'"Reclassified" column: 1990-91 moved supply_shock&harr;mixed, 2001 moved '
            f'demand_monetary&harr;mixed -- the two boundary-case episodes\' sensitivity check. '
            f'Grayed rows are below the n=5 gate: mean shown for context, not a tested claim.</p>'
            f'<table><thead><tr><th>Sub-type</th><th>Asset</th><th>n</th>'
            f'<th>Avg return</th><th>Reclassified</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


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
.caveat{background:#eda10014;border:1px solid #eda10055;border-radius:12px;
padding:14px 16px;margin-bottom:20px;font-size:.85rem;line-height:1.55}
.caveat h2{font-size:.9rem;margin:0 0 6px;color:#a86a00}
.gated-row td{color:var(--text-muted);font-style:italic}
.sig-row td{color:var(--text-primary);font-weight:600}
.p2-legend{color:var(--text-muted);font-size:.76rem;margin:0 0 10px;line-height:1.5}
"""


def build_html() -> str:
    returns = rs.build_returns()
    tagged = rs.attach_regime(returns)
    corrs = rs.correlation_matrices(tagged)
    playbook = rs.regime_playbook(tagged)
    snap = rs.diagnostic_snapshot()
    bundle = rs.phase2_bundle(returns)

    parts = [
        f"<title>Cross-Asset Regime Study</title><style>{CSS}</style>",
        '<div class="viz-root">',
        "<h1>Cross-Asset Regime Study — Equities vs Commodities</h1>",
        '<p class="sub">Annual returns, 1928/1927/1953/1949-2025 (coverage varies by asset '
        '&mdash; see note below), tagged by NBER recession/expansion (FRED USREC). '
        "This is a <strong>historical/descriptive study, not a live regime-detection "
        "signal</strong> &mdash; NBER recession dates are announced retrospectively, often "
        "12+ months after the fact, so nothing here says what regime we're in right now. "
        "Companion to the <a href=\"dashboard.html\">live dashboard</a> and the standalone "
        '<a href="https://claude.ai/code/artifact/607d6807-6ffa-449a-9e3c-f001a14fb3d8" '
        'target="_blank" rel="noopener">100yr asset-class chart</a>.</p>',
        '<div class="caveat"><h2>Open question this study does not resolve</h2>'
        'Pooling 1926-2025 as one binary (recession/expansion) assumes the correlation '
        '<em>regime itself</em> is stable across a century that includes the gold standard '
        '(pre-1971), the fiat-float era, and post-2008 unconventional monetary policy. It '
        "plausibly isn't. This study doesn't test for that -- a rolling or era-split "
        "correlation would be the next step (not built here). Treat every number below as "
        "\"how this behaved across 1926-2025 on average,\" not \"how this behaves today.\""
        '</div>',
        _trajectory_svg(returns, tagged),
        _significance_table_html(
            "Episode-level correlation — recession (headline)",
            bundle["episode_correlation_recession"],
            "PRIMARY cut: one compounded-return observation per recession episode (not "
            "per year) -- see the caveat above and docs/RECESSION_EPISODES.md. This is "
            "the authoritative number when it disagrees with the plain heatmaps below."),
        _significance_table_html(
            "Episode-level correlation — expansion",
            bundle["episode_correlation_expansion"], ""),
        '<p class="p2-legend">p/q legend: q is the Benjamini-Hochberg FDR-adjusted p-value, '
        'corrected jointly across every test in this report (not per-cell) -- a pair counts '
        'as significant only at <strong>q&lt;0.05</strong> (bold rows), not raw p&lt;0.05. '
        '"Not significant" means underpowered at this sample size, not "zero relationship" '
        '-- read it as inconclusive, not as a negative finding.</p>',
        _regime_significance_html(bundle["regime_significance"]),
        _subtype_html(bundle["sub_regime_sensitivity"]),
        _significance_table_html(
            "Common-window check (1953-2025, all 5 assets, apples-to-apples) — recession",
            bundle["common_window_recession"],
            "Confirmatory secondary cut: restricts every asset to copper's 1953-2025 "
            "window before recomputing, so no pair gets extra years the others lack."),
        _heatmap_svg("Extended history (1928-2025, mixed sample windows per pair)",
                     corrs["full_period"],
                     "Legacy/secondary view: raw Pearson r only, no significance test, each "
                     "pair uses whichever years both series happen to have -- e.g. "
                     "equities-vs-gold spans ~98 years but equities-vs-copper only ~72. Kept "
                     "for continuity with the original correlation view; the episode-level "
                     "tables above are authoritative when they disagree."),
        _heatmap_svg("Extended history — recession years only", corrs["recession"],
                     "Same mixed-window caveat as above, recession years only."),
        _heatmap_svg("Extended history — expansion years only", corrs["expansion"],
                     "Same mixed-window caveat as above, expansion years only."),
        _playbook_table(playbook),
        _diagnostics_card(snap),
        "<footer>Nominal, not inflation-adjusted. Silver is derived (NY gold price / "
        "MeasuringWorth gold-silver ratio) -- USGS Data Series 140 and Macrotrends both "
        "block automated fetches (WAF/Cloudflare challenge); anchor-checked against "
        "1980/2011/2020 spot prices and, for the pre-1968 span, against an independently "
        "documented ~$0.90/oz mid-1950s reference and the well-known $1.29/oz 1965 "
        "coinage-debasement threshold. Copper is a PPI index (FRED WPU102502, Dec 1953-), "
        "not a $/lb spot price. Pre-1934 gold (and pre-1968 silver) reflects "
        "government-fixed prices for part of their history, not a continuously freely "
        "traded market. Oil begins 1949 (EIA first continuous series). Episode return "
        "figures compound every calendar year an episode touches (annual data can't slice "
        "a mid-year recession boundary exactly) -- a documented approximation, not a monthly "
        "figure.</footer>",
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
