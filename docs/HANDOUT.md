# US Recession / Bubble-Risk Monitor — Project Handout

*A disciplined, backtested composite signal for late-cycle and crash risk. It does not
predict crashes — it produces a repeatable, bias-checked probability gauge and says
exactly why, and what would change the call.*

---

## 1. The idea: "kindling vs spark"

A market can be **expensive for years** without crashing. Overvaluation is the *kindling* —
it makes the system fragile but doesn't set the fire. The *spark* is the cluster of
credit, labor, and liquidity triggers that actually ignite a recession. This project keeps
the two **explicitly separate** so a stretched valuation is never mistaken for an imminent
crash. The headline you read is the **regime** (where we are) and the **trip-wires armed**
(the action signal) — not the raw composite number.

## 2. How the signal is built (pipeline)

```
raw indicators ──▶ 0–100 stress score ──▶ buckets ──▶ weighted composite ──▶ bands ──▶ regime
 (FRED/Yahoo/CAPE)   (historical percentile)  (4 families)   (backtest-calibrated)        + trip-wires
```

1. **Stress score (0–100) by historical percentile.** Each indicator is scored against its
   *own history*, not an absolute threshold — a CAPE of 38 only means something as "98th
   percentile since 1881." Backtests use a **date-causal** percentile (a past date is ranked
   only against prior rows) plus conservative release lags; the live read uses the full sample.
2. **Four buckets (weights):** Valuation 30% · Macro-Labor 40% · Credit 15% · Sentiment 15%.
   A bucket's score is the staleness-weighted mean of its indicators.
3. **Composite** = weighted mean of the buckets.
4. **Bands (checked on 1997–2021):** Normal <50 · Elevated 50–65 · Warning ≥65 ·
   Extreme ≥72. In the revision-adjusted rerun, ≥65 caught the GFC with 9m lead, missed
   dot-com and COVID, and fired in 15.0% of benign months. The regime map, not the bare
   score, is the headline.
5. **Trip-wires (6):** specific, watchable lines that would *confirm* a crash (curve inversion,
   Sahm rule, HY spread blowout, jobless-claims surge, VIX regime break, bank-standards crunch).
   "0/6 armed" is the disciplined all-clear; arming is the action signal.
6. **Regime map:** valuation level × trigger state → {Bubble/Excess, Fragile late-cycle, Crash
   watch, Triggered}, with a trigger override (≥2 armed escalates; ≥4 = active break).

## 3. Data sources

19 raw series (see `data_export/catalog.csv`): **FRED** (yield curves, Sahm rule, jobless
claims, core CPI, WTI, HY/IG credit spreads, bank lending standards, card delinquency, U.Mich
sentiment, savings rate), **Yahoo Finance** (S&P 500, VIX, 10y yield, dollar index, NVDA), and
**multpl/FRED-computed** valuation (Shiller CAPE, Buffett Indicator). A separate **AI-bubble
overlay** (hyperscaler capex, NVDA inventory, AI-infra credit spread — manual quarterly inputs)
is shown prominently but **kept out of the calibrated composite** so a stale/bespoke read can't
move the headline.

## 4. Key results (current read + history)

- **Today:** composite ≈ 69 (Warning), regime **Fragile late-cycle**, **0/6 trip-wires armed.**
  Valuation is at the 98th percentile — *higher than the 2000 dot-com peak* — while macro/credit
  triggers are quiet. Classic "expensive + calm": fuel maxed, spark absent.
- **History tells different bubble shapes** (`bubble_scorecard`): dot-com was **valuation-led**
  (valuation ~92 at the peak); the GFC was **credit/macro-led** (valuation only ~71, and it
  *collapsed* to ~49 at the Lehman burst as credit/sentiment spiked). Same composite, very
  different fuses — which is the whole point of separating the families.
- **"Where next?" (Markov transitions, 1999–2026):** from today's Warning bucket, historically
  over 6 months ≈ **44% stay / 28% worsen to Extreme / 28% ease** — a genuine fork, with more
  downside than from a merely Elevated reading.

## 5. Architecture (modules)

| Module | Role |
|---|---|
| `config.yaml` / `config.py` | all weights, bands, series IDs, trip-wires (tune here, not in code) |
| `data/fetch_*` + `cache_util.py` | fetch FRED/Yahoo/CAPE, date-stamped cache |
| `model/indicators.py` | raw data → 0–100 percentile stress (live + date-causal) |
| `model/scoring.py` | buckets, weighted composite, trend |
| `model/backtest.py` | 1997–2021 revision-adjusted/date-causal band check |
| `model/analytics.py` | trajectory, probabilities, analogs, regime, transition matrix |
| `output/verdict.py` | trip-wires + plain-English stance + bull-case defeaters |
| `output/dashboard.py` | self-contained HTML dashboard |
| `stats_utils.py` (V3) | shared causal z-score / YoY / standardization helpers |
| `features.py` (V3) | 31-feature registry (feature-store-lite) |

## 6. Honest limitations

- Base-rate "probabilities" are **historical frequencies conditional on the current bucket**,
  not calibrated predictions, and can co-occur — and rest on few *independent episodes* (n≈4 for
  stress regimes), so they are directional, not precise.
- A 16% benign false-positive rate is the cost of cleanly separating credit — the regime/trip-wire
  layer absorbs it.
- The historical sweep uses latest-vintage observations with conservative availability lags.
  It has no future rows, but is **not vintage-exact** because later revisions cannot be undone.
- The AI-overlay and some sentiment inputs are manual quarterly entries (lowest confidence).
- The model covers composite stress / base rates / trip-wires — **not** portfolio P&L or a joint
  asset distribution. It gives *lead*, not market *timing*.

## 7. Deliverables in this project

- **Dashboard:** `output/dashboard.html` (self-contained, open in any browser).
- **Data file:** `data_export/recession_dashboard_data.xlsx` (8 sheets — catalog, features, raw
  monthly, composite history, bubble scorecard, transition matrices). CSV copies alongside.
- **Setup/run guide:** `docs/PROJECT_INSTRUCTIONS.md`.
- **Methodology/eval notes:** `docs/v3_refactor_notes.md`, `docs/PHASE_3_REPORT.md`.

*Disciplined risk gauge, not investment advice.*
