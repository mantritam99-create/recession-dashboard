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
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
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

    print("[regime_study] demo OK "
          f"(returns n={len(returns)}, playbook rows={len(playbook)}, "
          f"diagnostics={len(snap)})")


if __name__ == "__main__":
    _demo()
    print(diagnostic_snapshot().to_string(index=False))
