"""Cross-asset regime study: equities vs commodities, tagged by NBER recession/expansion.

Reuses data/fetch_commodities_long.py (long-run annual series) and stats_utils.py
(rolling_zscore, FULL mode) rather than reimplementing either. Kept separate from
model/analytics.py, which drives the live daily dashboard on a different cadence.

Coverage caveat (real, not glossed over): only equities (1928-) and gold (1927-) reach
the full ~100yr window. Silver (derived) reaches back to 1791. Copper only has clean
data from 1953 (FRED WPU102502), oil from 1949 (EIA). Correlation matrices use pandas'
pairwise-complete `.corr()`, so each pair's sample window is whatever the two series
share -- e.g. equities-vs-gold uses ~98 years, equities-vs-copper only ~72. Report this
per-pair, don't imply one uniform 100yr window.

PHASE 2 -- statistical robustness (episode-level inference). Year-level correlation/
regime tests overstate statistical power: recession years cluster into a handful of
multi-year EPISODES (1929-33, 1973-75, 2007-09, ...), so "n=15 recession-years" is
really ~8-15 independent episodes, and a naive per-year t-test treats correlated years
as independent draws. Everything below the `PHASE 2` marker computes its primary
numbers on EPISODE-level data (one compounded-return observation per recession/
expansion episode, see `build_episode_returns()`), gates any test below
`MIN_N_EPISODES` to descriptive-only, and applies one joint Benjamini-Hochberg FDR
correction across every p-value produced (see `phase2_bundle()`). Year-level /
pairwise-complete numbers (the functions above this marker) are kept as a secondary,
explicitly lower-confidence view -- see `phase2_bundle()`'s docstring for the
resolution rule when the two disagree.

LOOKAHEAD / REAL-TIME-USE CAVEAT: NBER recession dates are announced retrospectively,
often 12+ months after the fact (via the Business Cycle Dating Committee). Every number
in this module is a historical/descriptive study of how asset classes behaved *after
the fact is known* which quarter was a recession -- it is not a live regime-detection
signal. Using this as "we're in expansion right now, so asset X should do Y" would be
circular: at any given moment, today's regime label doesn't exist yet.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from data import fetch_commodities_long as fcl
from stats_utils import rolling_zscore, FULL

ASSET_START = {"Equities (S&P 500 TR)": 1928, "Gold": 1927, "Silver (derived)": 1791,
               "Copper (PPI index)": 1953, "Oil (WTI-era)": 1949}


def _pct_return(level: pd.Series) -> pd.Series:
    return level.sort_index().pct_change().dropna()


def build_returns() -> pd.DataFrame:
    """Wide annual-return table, one column per asset, NaN where a series has no data
    yet for that year (pairwise-complete, not a dropped-to-shortest-common window)."""
    series = {
        "Equities (S&P 500 TR)": fcl.sp500_total_return(),
        "Gold": _pct_return(fcl.gold_price()),
        "Silver (derived)": _pct_return(fcl.silver_price_derived()),
        "Copper (PPI index)": _pct_return(fcl.copper_ppi_index()),
        "Oil (WTI-era)": _pct_return(fcl.oil_price()),
    }
    missing = [k for k, v in series.items() if v is None]
    if missing:
        raise RuntimeError(f"regime_study: no data for {missing} (fetch failed, no fallback)")
    return pd.concat(series, axis=1)


def attach_regime(returns: pd.DataFrame) -> pd.DataFrame:
    regime = fcl.recession_regime()
    if regime is None:
        raise RuntimeError("regime_study: NBER regime unavailable (FRED USREC fetch failed)")
    out = returns.copy()
    out["regime"] = regime.reindex(out.index)
    return out


def correlation_matrices(tagged: pd.DataFrame) -> dict[str, pd.DataFrame]:
    assets = [c for c in tagged.columns if c != "regime"]
    return {
        "full_period": tagged[assets].corr(),
        "recession": tagged.loc[tagged["regime"] == "recession", assets].corr(),
        "expansion": tagged.loc[tagged["regime"] == "expansion", assets].corr(),
    }


def regime_playbook(tagged: pd.DataFrame) -> pd.DataFrame:
    """asset x regime -> avg return, vol (std), n years, rank (1 = best avg return
    within that regime)."""
    assets = [c for c in tagged.columns if c != "regime"]
    rows = []
    for regime_name in ["recession", "expansion"]:
        sub = tagged.loc[tagged["regime"] == regime_name, assets]
        stats = pd.DataFrame({
            "avg_return": sub.mean(),
            "volatility": sub.std(),
            "n_years": sub.count(),
        })
        stats["rank"] = stats["avg_return"].rank(ascending=False, method="min").astype("Int64")
        stats.insert(0, "regime", regime_name)
        stats.insert(0, "asset", stats.index)
        rows.append(stats.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)


def diagnostic_snapshot() -> pd.DataFrame:
    """2 spread/ratio diagnostics, z-scored against their own full history (FULL mode
    per stats_utils convention -- this is a live-display snapshot, not a backtest, so
    lookahead is irrelevant). Returns one row per ratio with the latest value + z-score."""
    gold = fcl.gold_price()
    silver = fcl.silver_price_derived().reindex(gold.index).dropna()
    common = gold.index.intersection(silver.index)
    gold_silver_ratio = (gold.loc[common] / silver.loc[common]).dropna()

    copper = fcl.copper_ppi_index()
    common2 = gold.index.intersection(copper.index)
    g_idx = gold.loc[common2] / gold.loc[common2].iloc[0] * 100
    c_idx = copper.loc[common2] / copper.loc[common2].iloc[0] * 100
    gold_copper_relperf = (g_idx / c_idx).dropna()

    rows = []
    for name, s, note in [
        ("Gold/Silver ratio", gold_silver_ratio,
         "oz silver per oz gold -- monetary vs monetary+industrial split"),
        ("Gold/Copper relative performance", gold_copper_relperf,
         "growth-of-100 index ratio, since 1953 -- safe-haven vs industrial-cyclical gauge"),
    ]:
        z = rolling_zscore(s, window=len(s), mode=FULL)
        rows.append({
            "ratio": name, "note": note,
            "latest_year": int(s.index[-1].year), "latest_value": round(float(s.iloc[-1]), 3),
            "zscore_vs_history": round(float(z.iloc[-1]), 2),
            "history_start": int(s.index[0].year), "n_years": len(s),
        })
    return pd.DataFrame(rows)


# ============================== PHASE 2 ====================================

# Recession episode boundaries, transcribed exactly from a live pull of FRED USREC
# (1926-01 to present) this session -- (start_year, end_year, category). Re-verified
# in _demo() against a fresh USREC pull so a future FRED revision fails loud instead
# of silently drifting from this hardcoded table. Category rationale + sourcing for
# each episode: docs/RECESSION_EPISODES.md. "mixed" = boundary case per that doc
# (1990-91 Gulf oil spike + S&L crisis; 2001 dot-com bust + 9/11 supply disruption) --
# see sub_regime_sensitivity() for what happens if these are reclassified.
RECESSION_EPISODES = [
    (1926, 1927, "demand_monetary"),
    (1929, 1933, "financial_credit"),
    (1937, 1938, "demand_monetary"),
    (1945, 1945, "demand_monetary"),
    (1948, 1949, "demand_monetary"),
    (1953, 1954, "demand_monetary"),
    (1957, 1958, "demand_monetary"),
    (1960, 1961, "demand_monetary"),
    (1970, 1970, "demand_monetary"),
    (1973, 1975, "supply_shock"),
    (1980, 1980, "supply_shock"),
    (1981, 1982, "demand_monetary"),
    (1990, 1991, "mixed"),
    (2001, 2001, "mixed"),
    (2008, 2009, "financial_credit"),
    (2020, 2020, "exogenous"),
]

MIN_N_EPISODES = 5          # below this, suppress the test -- descriptive only
N_BOOTSTRAP = 2000          # block-bootstrap resamples for CIs without a closed form
COMMON_WINDOW_START = 1953  # copper's constraint -- the apples-to-apples cut
_RNG = np.random.default_rng(20260720)


def _recession_years() -> set[int]:
    return {y for start, end, _ in RECESSION_EPISODES for y in range(start, end + 1)}


def _build_expansion_episodes() -> list[tuple[int, int]]:
    """Contiguous non-recession calendar-year spans, derived programmatically from
    RECESSION_EPISODES so the two lists can't silently drift apart."""
    rec_years = _recession_years()
    non_rec = sorted(set(range(1926, 2026)) - rec_years)
    groups: list[list[int]] = []
    for y in non_rec:
        if groups and y == groups[-1][-1] + 1:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [(g[0], g[-1]) for g in groups]


EXPANSION_EPISODES = _build_expansion_episodes()


def build_episode_returns(returns: pd.DataFrame, episodes) -> pd.DataFrame:
    """Collapse annual `returns` to ONE compounded-return observation per episode, per
    asset -- the primary unit of inference for Phase 2 (see module docstring). Annual
    data can't precisely slice a mid-year recession boundary (e.g. Sep 1929), so an
    episode's return compounds every calendar year it touches, start through end
    inclusive -- a documented approximation, not an exact monthly slice."""
    rows = {}
    for ep in episodes:
        start, end = ep[0], ep[1]
        key = (start, end)
        row = {}
        for asset in returns.columns:
            vals = [returns[asset].get(pd.Timestamp(f"{y}-01-01")) for y in range(start, end + 1)]
            vals = [v for v in vals if pd.notna(v)]
            if vals:
                cum = 1.0
                for v in vals:
                    cum *= (1 + v)
                row[asset] = cum - 1.0
        rows[key] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def _fisher_z_ci(r: float, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n < 4 or abs(r) >= 1:
        return (float("nan"), float("nan"))
    z = np.arctanh(r)
    se = 1 / np.sqrt(n - 3)
    zcrit = scipy_stats.norm.ppf(1 - alpha / 2)
    return float(np.tanh(z - zcrit * se)), float(np.tanh(z + zcrit * se))


def _block_bootstrap_corr(sub: pd.DataFrame, a: str, b: str, kind: str,
                           n_boot: int = N_BOOTSTRAP) -> tuple[float, float] | None:
    """Percentile-bootstrap 95% CI, resampling whole EPISODE ROWS with replacement (not
    individual years) -- preserves within-episode structure instead of pretending
    clustered years are independent draws. Vectorized over all n_boot resamples at once
    (numpy, no per-iteration scipy call) -- a naive python-loop version of this timed
    out in practice at n_boot=2000 across ~60 pair/cut combinations."""
    n = len(sub)
    if n < MIN_N_EPISODES:
        return None
    av, bv = sub[a].to_numpy(), sub[b].to_numpy()
    idx = _RNG.integers(0, n, size=(n_boot, n))
    A, B = av[idx], bv[idx]
    if kind == "spearman":
        A = scipy_stats.rankdata(A, axis=1)
        B = scipy_stats.rankdata(B, axis=1)
    mA, mB = A.mean(axis=1, keepdims=True), B.mean(axis=1, keepdims=True)
    sA, sB = A.std(axis=1), B.std(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = ((A - mA) * (B - mB)).mean(axis=1) / (sA * sB)
    r = r[np.isfinite(r)]
    if len(r) < n_boot // 2:
        return None
    lo, hi = np.percentile(r, [2.5, 97.5])
    return float(lo), float(hi)


def _significance_table(df: pd.DataFrame, cut_label: str) -> pd.DataFrame:
    """Pairwise Pearson r (+ Fisher-z 95% CI) and Spearman rho (+ block-bootstrap 95%
    CI), n-gated at MIN_N_EPISODES. Works on any wide asset-return table -- episode-level
    (rows = episodes) or year-level (rows = years); the gate name references episodes
    for consistency with the Phase-2 design but is really just a minimum-sample floor."""
    assets = list(df.columns)
    rows = []
    for i in range(len(assets)):
        for j in range(i + 1, len(assets)):
            a, b = assets[i], assets[j]
            sub = df[[a, b]].dropna()
            n = len(sub)
            row = {"cut": cut_label, "asset_a": a, "asset_b": b, "n_effective": n,
                   "gated": n < MIN_N_EPISODES}
            if n < MIN_N_EPISODES:
                row.update(dict.fromkeys(
                    ["pearson_r", "pearson_p", "pearson_ci_lo", "pearson_ci_hi",
                     "spearman_rho", "spearman_p", "spearman_ci_lo", "spearman_ci_hi"]))
            else:
                r, p = scipy_stats.pearsonr(sub[a], sub[b])
                ci_lo, ci_hi = _fisher_z_ci(r, n)
                rho, sp = scipy_stats.spearmanr(sub[a], sub[b])
                boot = _block_bootstrap_corr(sub, a, b, "spearman")
                row.update({
                    "pearson_r": round(float(r), 3), "pearson_p": float(p),
                    "pearson_ci_lo": round(ci_lo, 3), "pearson_ci_hi": round(ci_hi, 3),
                    "spearman_rho": round(float(rho), 3), "spearman_p": float(sp),
                    "spearman_ci_lo": round(boot[0], 3) if boot else None,
                    "spearman_ci_hi": round(boot[1], 3) if boot else None,
                })
            rows.append(row)
    return pd.DataFrame(rows)


def episode_correlation_significance(returns: pd.DataFrame) -> dict:
    """PRIMARY Phase-2 correlation cut: full-history episode-level recession/expansion
    (each asset's own full available history, pairwise-complete across episodes) --
    the headline number per the module docstring's resolution rule."""
    rec_df = build_episode_returns(returns, RECESSION_EPISODES)
    exp_df = build_episode_returns(returns, EXPANSION_EPISODES)
    return {
        "recession": _significance_table(rec_df, "episode_recession"),
        "expansion": _significance_table(exp_df, "episode_expansion"),
        "recession_episode_returns": rec_df,
        "expansion_episode_returns": exp_df,
    }


def pairwise_complete_significance(returns: pd.DataFrame) -> pd.DataFrame:
    """SECONDARY/legacy cut: plain year-level pairwise-complete correlation (adds p/CI
    on top of the raw r Phase 1's correlation_matrices() already shows). Each pair uses
    a different, mixed sample window -- explicitly lower-confidence, not the headline
    number when it disagrees with the episode-level cut above."""
    return _significance_table(returns, "full_history_pairwise_complete_year_level")


def common_window_analysis(returns: pd.DataFrame) -> dict:
    """Apples-to-apples secondary check: every asset restricted to the shared
    COMMON_WINDOW_START-2025 window before computing full/recession/expansion
    significance. If this disagrees with the full-history episode cut, the gap is how
    much of that cut's result comes from which years each asset happens to cover."""
    w = returns[returns.index.year >= COMMON_WINDOW_START]
    rec_df = build_episode_returns(w, RECESSION_EPISODES)
    exp_df = build_episode_returns(w, EXPANSION_EPISODES)
    return {
        "full": _significance_table(w, "common_window_full_years"),
        "recession": _significance_table(rec_df, "common_window_episode_recession"),
        "expansion": _significance_table(exp_df, "common_window_episode_expansion"),
    }


def regime_significance_tests(returns: pd.DataFrame) -> pd.DataFrame:
    """Per-asset: is the recession-vs-expansion return gap even real? Welch's t-test
    (unequal variance) + Mann-Whitney U (non-parametric, safer for small/non-normal
    samples), both on EPISODE-level compounded returns. N-gated per side."""
    rec_df = build_episode_returns(returns, RECESSION_EPISODES)
    exp_df = build_episode_returns(returns, EXPANSION_EPISODES)
    rows = []
    for asset in returns.columns:
        r = rec_df[asset].dropna() if asset in rec_df else pd.Series(dtype=float)
        e = exp_df[asset].dropna() if asset in exp_df else pd.Series(dtype=float)
        n_r, n_e = len(r), len(e)
        gated = n_r < MIN_N_EPISODES or n_e < MIN_N_EPISODES
        row = {"asset": asset, "n_recession_episodes": n_r, "n_expansion_episodes": n_e,
               "gated": gated, "recession_mean": r.mean() if n_r else None,
               "expansion_mean": e.mean() if n_e else None,
               "welch_t": None, "welch_p": None, "mannwhitney_u": None, "mannwhitney_p": None}
        if not gated:
            t, p_t = scipy_stats.ttest_ind(r, e, equal_var=False)
            u, p_u = scipy_stats.mannwhitneyu(r, e, alternative="two-sided")
            row.update({"welch_t": round(float(t), 3), "welch_p": float(p_t),
                        "mannwhitney_u": float(u), "mannwhitney_p": float(p_u)})
        rows.append(row)
    return pd.DataFrame(rows)


def sub_regime_playbook(returns: pd.DataFrame, reclassify: dict | None = None) -> pd.DataFrame:
    """asset x sub-type (supply_shock / demand_monetary / financial_credit / exogenous /
    mixed) -> avg_return, std_return, n_effective, gated. Descriptive only, by design --
    per the module docstring, most sub-type buckets fall under MIN_N_EPISODES once
    recession episodes are split this finely, so no significance test is attached here
    (there'd be nothing valid to attach it to). `reclassify` optionally remaps specific
    (start,end) episodes to a different category, for the boundary-case sensitivity
    check -- see sub_regime_sensitivity()."""
    cats = {(s, e): c for s, e, c in RECESSION_EPISODES}
    if reclassify:
        cats.update(reclassify)
    ep_df = build_episode_returns(returns, RECESSION_EPISODES)
    rows = []
    for cat in sorted(set(cats.values())):
        keys = [k for k, c in cats.items() if c == cat]
        sub = ep_df.loc[ep_df.index.isin(keys)]
        for asset in returns.columns:
            vals = sub[asset].dropna() if asset in sub else pd.Series(dtype=float)
            n = len(vals)
            rows.append({
                "sub_type": cat, "asset": asset, "n_effective": n, "gated": n < MIN_N_EPISODES,
                "avg_return": float(vals.mean()) if n else None,
                "std_return": float(vals.std()) if n > 1 else None,
            })
    return pd.DataFrame(rows)


def sub_regime_sensitivity(returns: pd.DataFrame) -> pd.DataFrame:
    """Reclassify the two boundary episodes (1990-91 -> supply_shock instead of mixed;
    2001 -> demand_monetary instead of mixed) and report whether avg_return moves --
    the sensitivity check the module docstring/plan calls for on those two calls."""
    base = sub_regime_playbook(returns).rename(columns={"avg_return": "avg_return_base"})
    alt = sub_regime_playbook(returns, reclassify={
        (1990, 1991): "supply_shock", (2001, 2001): "demand_monetary",
    }).rename(columns={"avg_return": "avg_return_reclassified"})
    merged = base.merge(
        alt[["sub_type", "asset", "avg_return_reclassified", "n_effective", "gated"]],
        on=["sub_type", "asset"], how="outer", suffixes=("", "_alt"))
    return merged


def apply_fdr(tables: list[tuple[str, pd.DataFrame, str]]) -> None:
    """Benjamini-Hochberg FDR correction, jointly across every (df, p-column) pair in
    `tables` (label, df, pcol) -- mutates each df in place, adding f'{pcol}_q'. One joint
    pass over the WHOLE Phase-2 output, not per-table, so "significant" means q<0.05
    across everything tested, not raw p<0.05 on one cell in isolation."""
    flat_p, flat_loc = [], []
    for label, df, pcol in tables:
        if pcol not in df.columns:
            continue
        for idx in df.index:
            p = df.at[idx, pcol]
            if pd.notna(p):
                flat_p.append(p)
                flat_loc.append((label, idx, pcol))
    for _, df, pcol in tables:
        df[f"{pcol}_q"] = None
    if not flat_p:
        return
    q_all = scipy_stats.false_discovery_control(np.array(flat_p), method="bh")
    label_to_df = {label: df for label, df, _ in tables}
    for (label, idx, pcol), q in zip(flat_loc, q_all):
        label_to_df[label].loc[idx, f"{pcol}_q"] = float(q)


def phase2_bundle(returns: pd.DataFrame) -> dict:
    """Everything Phase 2 produces, FDR-corrected jointly. RESOLUTION RULE when cuts
    disagree: episode-level (episode_correlation_significance) is authoritative;
    common_window_analysis is a confirmatory apples-to-apples check;
    pairwise_complete_significance (year-level, mixed windows) is secondary/legacy,
    kept for continuity with Phase 1's raw-r heatmaps but explicitly lower-confidence."""
    ep_corr = episode_correlation_significance(returns)
    pw_corr = pairwise_complete_significance(returns)
    cw = common_window_analysis(returns)
    regime_sig = regime_significance_tests(returns)
    sub_playbook = sub_regime_playbook(returns)
    sub_sensitivity = sub_regime_sensitivity(returns)

    tables_for_fdr = [
        ("episode_recession", ep_corr["recession"], "pearson_p"),
        ("episode_recession", ep_corr["recession"], "spearman_p"),
        ("episode_expansion", ep_corr["expansion"], "pearson_p"),
        ("episode_expansion", ep_corr["expansion"], "spearman_p"),
        ("pairwise_complete", pw_corr, "pearson_p"),
        ("pairwise_complete", pw_corr, "spearman_p"),
        ("common_window_full", cw["full"], "pearson_p"),
        ("common_window_full", cw["full"], "spearman_p"),
        ("common_window_recession", cw["recession"], "pearson_p"),
        ("common_window_recession", cw["recession"], "spearman_p"),
        ("common_window_expansion", cw["expansion"], "pearson_p"),
        ("common_window_expansion", cw["expansion"], "spearman_p"),
        ("regime_significance", regime_sig, "welch_p"),
        ("regime_significance", regime_sig, "mannwhitney_p"),
    ]
    apply_fdr(tables_for_fdr)

    return {
        "episode_correlation_recession": ep_corr["recession"],
        "episode_correlation_expansion": ep_corr["expansion"],
        "pairwise_complete_correlation": pw_corr,
        "common_window_full": cw["full"],
        "common_window_recession": cw["recession"],
        "common_window_expansion": cw["expansion"],
        "regime_significance": regime_sig,
        "sub_regime_playbook": sub_playbook,
        "sub_regime_sensitivity": sub_sensitivity,
    }


# ============================ end PHASE 2 ===================================


def _demo():
    returns = build_returns()
    assert set(ASSET_START) == set(returns.columns), "asset columns mismatch"
    assert returns["Equities (S&P 500 TR)"].notna().sum() >= 90, "equities history too short"

    tagged = attach_regime(returns)
    assert tagged["regime"].dropna().isin(["recession", "expansion"]).all()
    assert set(tagged["regime"].dropna().unique()) == {"recession", "expansion"}, \
        "both regime classes must be present"

    corrs = correlation_matrices(tagged)
    for name, m in corrs.items():
        assert m.shape[0] == m.shape[1] == len(ASSET_START), f"{name} not square"
        assert np.allclose(m.fillna(0), m.fillna(0).T, atol=1e-9), f"{name} not symmetric"

    playbook = regime_playbook(tagged)
    assert len(playbook) == 2 * len(ASSET_START)

    snap = diagnostic_snapshot()
    assert snap["zscore_vs_history"].apply(np.isfinite).all(), "non-finite z-score"

    # ---- PHASE 2 asserts ----
    assert returns.abs().max().max() < 5, \
        "a return exceeds 500% -- check for accidentally-correlated price LEVELS, not returns"

    # RECESSION_EPISODES must exactly match a fresh USREC pull, or FRED revised history
    # and the hardcoded table has silently drifted.
    live_regime = fcl.recession_regime()
    live_rec_years = set(live_regime[live_regime == "recession"].index.year)
    hardcoded_rec_years = _recession_years()
    # live_regime uses a >=50%-of-months-per-year rule (coarser than the exact monthly
    # USREC boundaries RECESSION_EPISODES was built from), so it's a subset check, not
    # equality -- every year the coarse annual flag calls "recession" must appear in the
    # exact episode table; the reverse doesn't hold by construction (partial-year edges).
    missing = live_rec_years - hardcoded_rec_years
    assert not missing, f"RECESSION_EPISODES missing years the live USREC pull flags: {missing}"

    ep_corr = episode_correlation_significance(returns)
    for name, tbl in ep_corr.items():
        if name.endswith("_returns"):
            continue
        for col in ("pearson_p", "spearman_p"):
            vals = tbl[col].dropna()
            assert vals.between(0, 1).all(), f"{name}.{col} out of [0,1]"
        assert (tbl.loc[tbl["gated"], "pearson_p"].isna().all()
                and tbl.loc[~tbl["gated"], "pearson_p"].notna().all()), \
            f"{name}: gate flag and pearson_p nullness disagree"

    # n-gate must actually suppress output on a synthetic tiny (n=2) bucket.
    tiny = pd.DataFrame({"A": [0.1, -0.2], "B": [0.05, 0.03]})
    tiny_sig = _significance_table(tiny, "synthetic_tiny")
    assert tiny_sig["gated"].all() and tiny_sig["pearson_p"].isna().all(), \
        "n-gate did not suppress a below-threshold synthetic bucket"

    bundle = phase2_bundle(returns)
    for name, tbl in bundle.items():
        for col in tbl.columns:
            if col.endswith("_p") or col.endswith("_q"):
                vals = tbl[col].dropna()
                assert vals.between(0, 1).all(), f"{name}.{col} out of [0,1]"

    print("[regime_study] demo OK "
          f"(returns n={len(returns)}, playbook rows={len(playbook)}, "
          f"diagnostics={len(snap)}, phase2 tables={len(bundle)})")


if __name__ == "__main__":
    _demo()
    print(diagnostic_snapshot().to_string(index=False))
