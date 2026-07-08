# Run log

Continuity file. Each `main.py` run appends: date, live-indicator count,
danger-zone count, and the highest-stress indicators. Over months this is the
record of how your own signal evolved — the most valuable artifact here.

## Build progress
- [x] **Milestone 1 — data layer + normalization**
  - FRED (keyed API), Yahoo market (keyless), multpl CAPE (keyless), date-stamped cache
  - percentile-based 0-100 stress scoring (`model/indicators.py`)
- [x] **Milestone 2 — `model/scoring.py`**: 3-bucket weighted composite + breadth adjustment + coverage-based confidence interval
- [x] **Milestone 3 — `model/backtest.py`**: point-in-time sweep 1997-2021 (no lookahead)
  - CALIBRATION: composite **>=70** caught 2000 top (18m lead) & 2007 top (8m lead),
    correctly MISSED exogenous COVID, fired in only **7.5%** of benign months.
    Non-events (2011/15/18) peaked <=60. -> 70 = warning line, 80 = acute. (in `config.yaml bands`)
- [x] **Milestone 4 — `output/verdict.py`**: stance + "what would confirm" trip-wires + bull-case-defeaters panel
- [x] **Milestone 5 — `output/dashboard.py`**: self-contained HTML (no CDN) — confidence gauge,
  12-month composite trajectory (inline SVG), trip-wire proximity bars, bull-case panel,
  "moving most (3m)", full indicator table with deltas. Run `py -m output.dashboard`.
- [x] **AI-bubble layer wired** — `data/fetch_manual.py` reads `manual_inputs.csv` (calm/stress
  anchors, staleness-flagged) into the composite -> now 21 indicators.
- [x] **Momentum engine** — per-indicator 3m stress deltas + composite trajectory
  (`scoring.trend / composite_history / indicator_deltas`). "How the world is moving."
- [ ] Optional next — alerts/scheduling on threshold cross; AAII auto-scrape;
  accumulate manual history quarterly to switch it from anchors to true percentile scoring

---

### 2026-06-04 03:56
- live: 1/15 | danger-zone: 0
- highest stress: VIX (38)

### 2026-06-04 03:57
- live: 2/15 | danger-zone: 1
- highest stress: Shiller CAPE (99), VIX (38)

### 2026-06-04 03:59
- live: 14/15 | danger-zone: 5
- highest stress: U.Mich sentiment (100), Shiller CAPE (99), Personal savings rate (95)

### 2026-06-04 04:02
- composite **73.3** | confidence **51.3 +/-4** | breadth 0.4
- buckets val/macro/sent: 99.3 / 47.7 / 77.8
- live: 15/15 | danger-zone: 6
- highest stress: U.Mich sentiment (100), Shiller CAPE (99), Buffett Indicator (99)

### 2026-06-04 04:07
- composite **73.3** | confidence **51.3 +/-4** | breadth 0.4
- buckets val/macro/sent: 99.3 / 47.7 / 77.8
- live: 15/15 | danger-zone: 6
- highest stress: U.Mich sentiment (100), Shiller CAPE (99), Buffett Indicator (99)

### 2026-06-04 04:18
- composite **70.2** | confidence **45.1 +/-4** | breadth 0.29
- buckets val/macro/sent: 99.3 / 45.1 / 69.7
- live: 21/21 | danger-zone: 6
- highest stress: U.Mich sentiment (100), Shiller CAPE (99), Buffett Indicator (99)

### 2026-06-04 04:25
- composite **70.2** | confidence **45.1 +/-4** | breadth 0.29
- buckets val/macro/sent: 99.3 / 45.1 / 69.7
- live: 21/21 | danger-zone: 6
- highest stress: U.Mich sentiment (100), Shiller CAPE (99), Buffett Indicator (99)

### 2026-06-14 18:00
- composite **70.7** | confidence **45.4 +/-4** | breadth 0.29
- buckets val/macro/sent: 98.2 / 46.0 / 71.7
- live: 21/21 | danger-zone: 6
- highest stress: U.Mich sentiment (100), Shiller CAPE (99), Buffett Indicator (97)

### 2026-06-20 14:09
- composite **69.0** | confidence **44.3 +/-4** | breadth 0.29
- buckets: valuation 98.2 / macro-labor 61.7 / credit 28.1 / sentiment 70.8
- live: 21/21 | danger-zone: 6
- highest stress: U.Mich sentiment (100), Shiller CAPE (99), Buffett Indicator (97)

### 2026-07-08 10:16
- composite **86.8** | confidence **59.6 +/-26** | breadth 0.38
- buckets: valuation 99.2 / macro-labor None / credit None / sentiment 61.8
- live: 8/21 | danger-zone: 3
- highest stress: Insider buy/sell ratio (100), Margin debt YoY% (100), Shiller CAPE (99)
