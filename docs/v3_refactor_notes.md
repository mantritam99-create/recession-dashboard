# V3 refactor — running notes

Branch: `feature/v3-refactor`. Test command: **`py -m pytest`** (pytest 9.1.1 installed; see
`requirements-dev.txt`). Working dir for runs: the repo root; run modules by file path
(`py output/dashboard.py`) since the shell cwd may be Desktop, not the repo.

---

## Phase 0 — repo audit + safety net (DONE)

**Files read:** dashboard.py, analytics.py, scoring.py, indicators.py, verdict.py, backtest.py,
config.yaml, config.py, cache_util.py, main.py (all reviewed during the v2 work in this session + re-cited
below).

### 1. Date causality — correct; vintage correctness — not implemented
- `indicators.percentile_asof(series, asof, dir)` slices `series[series.index <= asof]` before ranking →
  strictly causal (no lookahead). Live `indicators.percentile_score(cur, history, dir)` ranks against the
  FULL series (correct for a live read).
- `scoring.composite_asof()` and `model/backtest.py` (`sweep = {d: composite_asof(loaded, d) ...}`) use the
  causal path. So future rows are excluded, but this alone is not point-in-time correctness.
- Revisions caveat: FRED series (Sahm, claims, CPI, Buffett inputs) are restated after first release; the
  pipeline fetches latest-vintage values. A later hardening pass added enforced conservative
  availability lags and explicit not-vintage-exact labels; no vintage database is built.

### 2. Confidence-by-source — display only
- `analytics.SRC_CONF` + `analytics.confidence_decomposition()` feed the dashboard `_confidence` panel,
  which itself says "data-quality weights, not statistical CIs". NOT used in composite math. Phase 1 →
  label "informational only."

### 3. Current scoring logic (v2)
indicator → 0-100 historical percentile (`indicators`) → staleness-weighted bucket mean (`scoring.composite`,
stale indicators keep `staleness.stale_weight`=0.4) → weighted composite. **Weights:** valuation 0.30 /
macro_labor 0.40 / credit 0.15 / sentiment 0.15. **Bands:** benign 50 / watch 58 / warning 65 / acute 72.
6 tripwires via `verdict.assess`. AI manual inputs live in bucket `overlay` (NOT in `weights`) → excluded
from composite by construction. 2s10s bucket = `context` (confirmation-only, excluded).

### 4. Data flow
`fetch_fred/fetch_market/fetch_valuation` → `indicators.load_all()` → `[(spec, series)]` → `indicators.compute()`
(adds manual rows) → `scoring.composite()` / `verdict.assess()` / `analytics.*` → `output/dashboard.build()`.
Cache: `cache_util` date-stamped CSV (series) / JSON (scalars), freshness by mtime.

### 5. Daily→monthly aggregation convention: month-END
`analytics._eom(p) = p.to_timestamp(how="end")`; `analytics.forward_returns` uses `spx.resample("ME").last()`.
**Reuse as-is in Phase 3 — do not invent a new resample rule.**

### 6. Test command
No pytest/Makefile existed (`requirements.txt` = pandas, pyyaml only; repo used `__main__` self-checks).
Installed pytest 9.1.1 → **`py -m pytest`**. Added `requirements-dev.txt`.

### 7. Existing validation coverage
`scoring._selfcheck_staleness()` (assert in `__main__`); `model/backtest.py` calibration table;
per-module `__main__` demos. No formal test suite before this phase.

### 8. Baseline snapshot fixture + enforcement test
`tests/snapshots/v2_baseline.json` + `tests/test_baseline_snapshot.py`. Captures, for the live read:
composite (69.0), buckets (val 98.2 / macro_labor 61.7 / credit 28.1 / sentiment 70.8), 6 tripwire
armed-states (all false, 0/6), prob bucket ("70+") + recession prob (10). And for 4 as-of dates
(2000-03, 2007-10, 2020-03, 2024-12 — the "expensive + calm" stretched pick) the causal composite +
buckets. Strict on discrete fields, EPS=0.5 on floats (absorbs data-revision noise, catches refactor bugs).
**Status: PASSES now** (`py -m pytest tests/` → 1 passed). This is the regression gate for Phases 1-3.

### Known limitations / TODO for later phases
- Baseline EPS tolerance is for within-session stability; across data refetches the live composite drifts
  (expected). Historical as-of values are the durable lock.
- Factor families are thin (~15 raw series); PCA value is questionable for growth/labor/inflation — to be
  judged at the Phase 3 STOP gate.
- sklearn/hmmlearn install on Python 3.14 not yet verified (Phase 4 concern).

---

## Phase 1 — correctness/honesty fixes (DONE)

**Files touched:** `stats_utils.py` (new), `tests/test_pit.py` (new), `model/analytics.py`,
`output/dashboard.py`, `config.yaml`.

1. **PIT — assert, not repair.** Phase 0 confirmed `percentile_asof` is causal. Added `tests/test_pit.py`:
   appending future data must not change a past as-of score (passes). Also locks `stats_utils.rolling_zscore`
   PIT mode against look-ahead.
2. **Shared causal helper `stats_utils.py`** — `Mode(point_in_time)`, `PIT`/`FULL`, `rolling_zscore`
   (PIT=trailing rolling, FULL=global), `pct_change_yoy` (frequency-agnostic, year-ago via reindex+ffill,
   inherently causal), `standardize_features` (PIT=expanding, FULL=global). `__main__` demo asserts.
   **Every later phase MUST use these** — no reimplementation.
3. **Probability honesty (additive, values unchanged).** `analytics.probabilities` now returns `note`
   (conditional historical frequencies, not calibrated predictions, can co-occur) + `n_episodes`
   (contiguous same-bucket runs). Dashboard `_prob_panel` shows "n=… mo across N independent episodes" +
   the note. Probability VALUES are unchanged.
4. **Confidence-by-source** labeled "Informational only — not applied to composite math" in
   `_confidence` panel (it never was load-bearing; no re-wiring).
5. **`revisions_policy`** began as documentation only. It is now enforced by backtests: every loaded
   series is classified, revision-prone sources are conservatively lagged, and outputs say date-causal,
   not vintage-exact. No vintage DB is built.

**Validation:** `py -m pytest` → 3 passed (baseline + 2 PIT). **Baseline snapshot GREEN — current-date
composite/bucket/tripwires/probs UNCHANGED.** No historical fixture deltas (no scoring math changed; PIT was
already correct). Dashboard builds clean.

---

## Phase 2 — feature registry MVP (DONE)

**Files touched:** `features.py` (new), `model/indicators.py` (+`load_raw_data`), `tests/test_features.py` (new).

- `FeatureDef` + `FEATURE_REGISTRY` = **31 features** from existing indicators only, via `stats_utils`
  (causal). Per family: growth 5, labor 4, inflation 3, **credit 7**, liquidity 4, valuation 4, sentiment 4.
- Discipline applied: trending series (CPI, WTI, SPX, NVDA, DXY) use YoY (stationary), not level z-scores;
  2s10s kept level-only (skip its z — correlated with 3m10y); claims uses yoy not 4w/13w MA. Comments note skips.
- `compute_features(raw_data, mode, freq)` resamples each raw series to month-END (Phase 0 convention),
  `ffill(limit=3)` to carry quarterly series (bank standards, cc delinq, Buffett) across intra-quarter gaps,
  then applies transforms. Defaults to FULL mode (live); `su.PIT` available for causal use.
- `indicators.load_raw_data()` returns raw levels keyed by FRED code/ticker/'cape'/'buffett' (includes
  context tickers ^GSPC/^TNX/DX/NVDA). NO yoy pre-applied — registry owns transforms.
- **NOT wired into the composite** — side-by-side/inspectable only.

**Validation:** `py -m pytest` → 5 passed; baseline still GREEN. `py features.py` → 31/31 computed.

**Realism note for the Phase 3 gate:** the panel index spans 1881–2026 (CAPE's long history); restrict to a
common post-1990 window for PCA. Family raw-series breadth is the real constraint: **credit (4 raw series)
is the only family deep enough for meaningful PCA**; growth/labor/inflation/valuation are 1–2 raw series
each (PC1 ≈ the series). This is the evidence that will shape the Phase 3 recommendation on factors/HMM.

---

## Phase 3 — Markov transition matrix + STOP (DONE; awaiting go-ahead for Phase 4+)

**Files touched:** `model/analytics.py` (+REGIME_BUCKETS, regime_bucket, bucket_series_monthly,
transition_counts, compute_transition_matrix, transition_summary), `output/dashboard.py`
(+`_transition_panel`, wired under the trajectory), `docs/PHASE_3_REPORT.md` (new — the STOP evidence report).

- Buckets = v2 display bands (Normal<50 / Elevated 50-65 / Warning 65-72 / Extreme ≥72). NOTE: left the
  stale `analytics.COMP_BUCKETS` (55/65/70, used by the probability panel + locked in the baseline) UNTOUCHED
  per "don't tidy unrelated code" — flagged here as a known inconsistency for a future cleanup.
- 330 monthly obs (1999-2026), Laplace-smoothed, row-normalized; dashboard shows the current bucket's
  3m/6m stay/ease/worsen split. `py -m pytest` → 5 passed; baseline GREEN.

**Key findings (full report: docs/PHASE_3_REPORT.md):** persistence is a strong real signal (diagonals far
above base rate); the current **Warning** row is genuinely useful (6m: 44% stay / 28% worsen / 28% ease);
but stress buckets are episode-dominated (~4 Extreme episodes) so fine-grained forecasting is noisy.

**RECOMMENDATION: do NOT proceed to PCA/HMM (Phase 4) as specced** — factor families are too thin (only
credit has depth; PC1 ≈ the series elsewhere), and an HMM on ~4 stress episodes would overfit (plus
hmmlearn on py3.14 unverified). Cheaper higher-value step: a *conditional* transition matrix (split the
Warning row by credit-calm/stressed or tripwire count). Phases 5–6 (snapshot/daily-note) are worthwhile
independently if desired. **STOP — awaiting explicit go-ahead.**
