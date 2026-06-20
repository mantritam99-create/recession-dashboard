# Phase 3 — Markov Transition Matrix: Evidence Report (MANDATORY STOP)

Monthly composite regime buckets, 1999-01 → 2026-06 (**330 months**), causal
(`composite_asof`, month-end). Buckets use the v2 display bands (same as the
trajectory/`zone_of`), NOT the stale 55/65/70 probability buckets:

| bucket | range | label |
|---|---|---|
| 0 | <50 | Normal |
| 1 | 50–65 | Elevated |
| 2 | 65–72 | Warning |
| 3 | ≥72 | Extreme |

**Unconditional distribution:** Normal 11% · Elevated 53% · Warning 24% · Extreme 12%.
**Current bucket: Warning.**

## 1. Transition matrices (row = from, % to each)

**1-month**
| from＼to | Normal | Elevated | Warning | Extreme |
|---|---|---|---|---|
| Normal | **64** | 34 | 1 | 1 |
| Elevated | 7 | **87** | 5 | 0 |
| Warning | 1 | 10 | **73** | 15 |
| Extreme | 1 | 1 | 29 | **69** |

**3-month**
| from＼to | Normal | Elevated | Warning | Extreme |
|---|---|---|---|---|
| Normal | **42** | 55 | 1 | 1 |
| Elevated | 12 | **78** | 11 | 0 |
| Warning | 1 | 18 | **54** | 27 |
| Extreme | 1 | 3 | 48 | **48** |

**6-month**
| from＼to | Normal | Elevated | Warning | Extreme |
|---|---|---|---|---|
| Normal | **42** | 55 | 1 | 1 |
| Elevated | 12 | **71** | 14 | 4 |
| Warning | 1 | 28 | **44** | 28 |
| Extreme | 1 | 8 | 56 | 35 |

## 2. Divergence from the unconditional baseline

A χ² goodness-of-fit is **not valid here** — many cells have expected counts <5,
and monthly observations are heavily autocorrelated (consecutive months are not
independent draws), so a p-value would be false precision (exactly the failure
mode this refactor exists to avoid). Qualitatively:

- Diagonal persistence massively exceeds the unconditional base rate (Elevated→Elevated
  87% vs 53% base; Warning→Warning 73% vs 24%; Extreme→Extreme 69% vs 12% at 1m).
  **Persistence is a strong, real signal.**
- Off-diagonal "where next" is weaker and episode-dominated (see §4).

## 3. Plain-language verdict per starting bucket

- **Normal** — *drifts up, doesn't stay pristine.* Mean-reverts toward Elevated (34%→55% by 3m); essentially never jumps straight to stress (structural: can't skip buckets monthly).
- **Elevated** — *the gravity well.* Extremely sticky (87% 1m, 71% 6m). The market's default resting state; noisy but persistent.
- **Warning (today)** — *a genuine fork.* Sticky at 1m (73%) but over 6m splits ~evenly: **44% stay, 28% worsen to Extreme, 28% ease to Elevated.** Materially higher worsen-odds than from Elevated (which is ~4% to Extreme at 6m). This is the most decision-useful row, and it's the one we're in.
- **Extreme** — *sticky, then bleeds to Warning, not to calm.* 69% stays at 1m; by 6m 56% has decayed to Warning, only ~9% reaches Elevated, ≈0% to Normal. The hangover is long.

## 4. Limits & caveats

- **Episode-dominated stress buckets.** 330 months but only ~4 distinct Extreme episodes
  (2000-02, 2007-09, 2020, 2022) and a handful of Warning runs. Month-counts overstate
  independent evidence; effective n for the Extreme/Warning rows is a few episodes, not dozens.
- **Small cells (raw counts):** Extreme→Elevated @6m = 3; Extreme→Normal = 0 across all horizons;
  Normal→Warning/Extreme = 0 (structural). Treat any single off-diagonal stress cell as
  illustrative, not estimated. Bucket 3 (Extreme) at 6m rests on ~40 autocorrelated months ≈ 4 episodes.
- **Clustering:** Warning↔Extreme transitions are dominated by the GFC (2007-09) and 2022; the
  Extreme→Warning decay is largely GFC unwind + 2020 V-recovery. Different episodes, similar shape — mild reassurance, not independence.
- **Asymmetry:** easy to slide Elevated→Warning; hard to climb Extreme→Normal. Stress is stickier than calm.

## 5. Phase 1 fix deltas (affect trust in these numbers)

Phase 1 changed **no scoring math** — PIT was already causal, so the composite history feeding
this matrix is unchanged from v2 (baseline snapshot stayed GREEN). The honesty additions
(`note`, `n_episodes`, confidence-by-source labeling) are metadata. So these transition numbers
inherit the v2 composite exactly; the only trust caveat is the episode-count one above, not a Phase 1 delta.

## 6. One-line conclusion

**The transition matrix is genuinely useful for persistence and for the current Warning fork,
but mostly noise for fine-grained stress→stress forecasting given ~4 effective episodes.**

## 7. Recommendation (honest, even against the roadmap)

**Do NOT proceed to the PCA factor layer + HMM as specced.** Two reasons, both already evidenced:

1. **The factor layer is theater on this data.** Only the *credit* family has enough independent raw
   series (4) for PCA to mean anything; growth/labor/inflation/valuation are 1–2 raw series each, so
   PC1 ≈ the series. A 4-state Gaussian HMM on 5 such "factors" (≈ a handful of episodes of real stress)
   would be unstable and overfit — and hmmlearn wheels on Python 3.14 are unverified.
2. **The cheap matrix already captures the persistence signal** an HMM would mostly rediscover.

**Higher-value, cheaper next step instead:** make the transition matrix *conditional* — e.g. split the
Warning row by whether **credit is calm vs stressed** (or by tripwire count). That directly sharpens
"where next" with a transparent 2-factor table, no latent-state machinery, and it leans on the one
family (credit) that actually has depth. Optionally extend history pre-1999 to add Extreme episodes.

If you still want the snapshot/daily-note plumbing (Phases 5–6), those are worthwhile regardless of the
factor decision and could proceed independently of PCA/HMM.

---
**STOP — awaiting explicit go-ahead before Phase 4/5/6.**
