# V3 refactor — running notes

Branch: `feature/v3-refactor`. Test command: **`py -m pytest`** (pytest 9.1.1 installed; see
`requirements-dev.txt`). Working dir for runs: the repo root; run modules by file path
(`py output/dashboard.py`) since the shell cwd may be Desktop, not the repo.

---

## Phase 0 — repo audit + safety net (DONE)

**Files read:** dashboard.py, analytics.py, scoring.py, indicators.py, verdict.py, backtest.py,
config.yaml, config.py, cache_util.py, main.py (all reviewed during the v2 work in this session + re-cited
below).

### 1. Point-in-time integrity — ALREADY CORRECT in the backtest path
- `indicators.percentile_asof(series, asof, dir)` slices `series[series.index <= asof]` before ranking →
  strictly causal (no lookahead). Live `indicators.percentile_score(cur, history, dir)` ranks against the
  FULL series (correct for a live read).
- `scoring.composite_asof()` and `model/backtest.py` (`sweep = {d: composite_asof(loaded, d) ...}`) use the
  causal path. So historical scoring is frozen-at-date already. **Phase 1 fix #1 = add an asserting test +
  comment, not a repair.**
- Revisions caveat: FRED series (Sahm, claims, CPI, Buffett inputs) are restated after first release; the
  pipeline fetches latest-vintage and treats it as if available at the as-of date. Not a vintage DB; will
  add a `revisions_policy` note in config in Phase 1 (conservative, documented; not building vintages).

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
