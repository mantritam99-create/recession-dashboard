# Recession / Bubble-Risk Dashboard

A disciplined, **backtested** composite signal for late-cycle / crash risk. It does
not predict crashes — it produces a repeatable, bias-checked probability gauge:
*"thesis confidence: 51%, here's exactly why, and here's what would change it."*

## What it does
1. Pulls ~15 macro / valuation / sentiment indicators (FRED + Yahoo + multpl).
2. Normalizes each to a **0–100 stress score by historical percentile** (a CAPE of
   42 only means something as "99th percentile since 1881").
3. Combines them into a **3-bucket weighted composite** (valuation / macro / sentiment),
   then applies a **breadth adjustment** — one screaming indicator ≠ conviction.
4. **Backtested** against 1997–2021 with strict no-lookahead to calibrate the threshold.
5. Emits a plain-English **verdict**, a **"what would confirm the crash" trip-wire checklist**,
   and a permanent **bull-case-defeaters** panel that fights your own confirmation bias.

## Quick start
```bash
pip install -r requirements.txt
# FRED key (free, 32-char) at https://fredaccount.stlouisfed.org/apikeys
# put it in config.yaml  fred.api_key:  OR  set env FRED_API_KEY
py main.py              # full run: indicators -> composite -> momentum -> verdict (+ appends log.md)
py -m model.backtest    # re-run historical calibration
py -m output.dashboard  # build output/dashboard.html, then open it in any browser
```
Individual modules are runnable for debugging: `py data/fetch_market.py`,
`py data/fetch_fred.py`, `py data/fetch_valuation.py`, `py model/indicators.py`,
`py model/scoring.py`, `py output/verdict.py`.

## Layout
```
config.yaml        all weights, thresholds, series IDs, bands, trip-wires (tune here, not in code)
config.py          config + path loader
cache_util.py      date-stamped cache (never refetch same-day data)
data/              fetch_fred.py · fetch_market.py · fetch_valuation.py · manual_inputs.csv
model/             indicators.py (normalize) · scoring.py (composite) · backtest.py (calibrate)
output/            verdict.py (stance + trip-wires + bull-case) · dashboard.py (self-contained HTML)
cache/             raw pulls (gitignored)
log.md             append-only run history — your signal's evolution over time
main.py            orchestrator
```

## Calibration (from `model/backtest.py`, 1997–2021, no lookahead)
| Threshold | Dot-com | GFC | COVID | Benign false-positive |
|-----------|---------|-----|-------|-----------------------|
| **≥70**   | 18m lead | 8m lead | (correctly) miss | **7.5%** |
| ≥75       | miss | miss | miss | 0.0% |

→ **70 = warning line, 80 = acute.** COVID *should* miss — it was exogenous; a model
that "predicted" it would be overfit. Re-run the backtest whenever you change weights.

## Honest limitations
- **FRED key required** for the macro bucket and the backtest (Yahoo + CAPE are keyless).
- **AI-bubble layer** (hyperscaler capex, NVDA inventory days, AI-infra spreads) and some
  sentiment (AAII, insider, margin debt) are **manual quarterly inputs** in
  `data/manual_inputs.csv` — not yet wired into the score (next step). Don't fake-automate them.
- **Forward P/E** is hard to get free; we use CAPE + Buffett for valuation instead.
- Buffett Indicator uses `NCBEILQ027S`/GDP (FRED dropped the Wilshire series); flagged for calibration.
- The signal gives **lead, not timing**. Use the trip-wire checklist as the action signal.
