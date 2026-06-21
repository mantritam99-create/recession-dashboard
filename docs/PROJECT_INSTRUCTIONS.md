# Project Instructions — setup, run, reproduce

## 1. Prerequisites

- **Python 3.10+** (developed/tested on 3.14).
- Install runtime deps:
  ```bash
  py -m pip install -r requirements.txt        # pandas, pyyaml (+ the data fetchers)
  ```
- Dev/extras (tests + Excel export):
  ```bash
  py -m pip install -r requirements-dev.txt     # pytest
  py -m pip install openpyxl                     # only for the .xlsx data export
  ```

## 2. FRED API key (free, required for the macro bucket + backtest)

The valuation (CAPE) and market (Yahoo) data are keyless, but the FRED macro/credit/labor
series need a free key (32-char) from <https://fredaccount.stlouisfed.org/apikeys>. Provide it
**either** way:

- **Local file (gitignored):** create `config.local.yaml`:
  ```yaml
  fred:
    api_key: "YOUR_32_CHAR_KEY"
  ```
- **or environment variable:** `FRED_API_KEY=YOUR_KEY`

Pulled data is cached date-stamped in `cache/` (gitignored), so you won't re-hit the APIs the
same day. The repo ships with a populated cache, so it runs offline out of the box.

## 3. Run it

Run from the **project root**. (If `py -m output.dashboard` fails with "No module named
output", your shell isn't in the repo root — run the file path form instead; it inserts the
root onto `sys.path` itself.)

| Command | What it does |
|---|---|
| `py main.py` | Full run: indicators → composite → verdict; prints the report and appends `log.md` |
| `py output/dashboard.py` | Builds `output/dashboard.html` (open it in any browser) |
| `py model/backtest.py` | Re-runs the 1999–2021 point-in-time band calibration |
| `py export_data.py` | Writes the consolidated data file to `data_export/` |
| `py -m pytest` | Runs the test suite (baseline snapshot, PIT lock, feature checks) |

Individual modules are runnable for debugging: `py model/indicators.py`, `py model/scoring.py`,
`py model/analytics.py`, `py features.py`, `py output/verdict.py`, `py stats_utils.py`.

## 4. Layout

```
config.yaml          weights, bands, series IDs, trip-wires (tune here, not in code)
config.py            config + path loader;  config.local.yaml  local secrets (FRED key)
cache_util.py        date-stamped cache;  cache/  raw pulls (gitignored)
data/                fetch_fred.py · fetch_market.py · fetch_valuation.py · fetch_manual.py
                     manual_inputs.csv  (AI-bubble overlay + manual sentiment, quarterly)
model/               indicators.py · scoring.py · backtest.py · analytics.py
output/              verdict.py · dashboard.py → dashboard.html
stats_utils.py       (V3) shared causal stats helpers
features.py          (V3) 31-feature registry
export_data.py       (V3) consolidated data export
tests/               pytest suite + snapshots/v2_baseline.json (regression net)
docs/                HANDOUT.md · PROJECT_INSTRUCTIONS.md · v3_refactor_notes.md · PHASE_3_REPORT.md
log.md               append-only run history
```

## 5. The data file

`py export_data.py` produces **`data_export/recession_dashboard_data.xlsx`** (one workbook,
8 sheets) — and CSV copies of each sheet if you don't have `openpyxl`:

| sheet | contents |
|---|---|
| `catalog` | 19 raw indicators: id, name, source, bucket, direction |
| `feature_catalog` | the 31-feature registry definitions |
| `raw_monthly` | every raw series, month-end, wide (date × indicator) |
| `features` | the computed 31-feature matrix |
| `composite_history` | monthly composite + regime bucket, 1999–2026 |
| `bubble_scorecard` | bucket stress at dot-com / GFC / COVID / today |
| `transition_3m`, `transition_6m` | Markov regime-transition matrices (%) |

## 6. Reproduce the headline results

```bash
py model/backtest.py        # prints lead-times: dot-com ~17m, GFC ~15m, COVID miss @ band 65
py output/dashboard.py      # current read: composite ~69, regime Fragile late-cycle, 0/6 armed
py -m pytest                # all green = the v2 scoring behavior is reproduced
```

## 7. Presenting it as a project — angles

- **Methodology:** percentile (relative) stress vs absolute thresholds; why no-look-ahead matters;
  bucket weighting + band calibration as an explicit, falsifiable design.
- **The finding:** today's valuation exceeds the 2000 peak yet 0/6 triggers are armed — and the
  historical scorecard shows dot-com (valuation-led) vs GFC (credit-led) were structurally different.
- **Engineering:** caching, point-in-time backtest, a regression-snapshot test, a feature registry,
  and the V3 Markov "where next?" layer.
- **Honesty:** the limitations section in `HANDOUT.md` (small effective episode counts, false-positive
  trade-off, lead-not-timing) is itself a talking point — it shows you understand the model's edges.

*Tip: convert `docs/HANDOUT.md` to PDF/Word for a printable handout (e.g. paste into a doc, or
`pandoc HANDOUT.md -o handout.pdf`). Ask and this can be generated for you.*
