"""Cross-asset regime study export -- mirrors export_data.py's pattern for a separate,
lower-cadence analysis (annual/100yr) rather than the live daily dashboard's data.

Writes to data_export/:
  - regime_study_master.csv       : long format, date x asset x price x return x vol x regime
  - regime_study_corr_full.csv    : full-period correlation matrix
  - regime_study_corr_recession.csv
  - regime_study_corr_expansion.csv
  - regime_study_playbook.csv     : asset x regime x avg_return x volatility x n_years x rank
  - regime_study_diagnostics.csv  : current-period ratio snapshot + z-score vs history

Run:  py export_regime_study.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

from config import ROOT
from data import fetch_commodities_long as fcl
from model import regime_study as rs

OUT_DIR = os.path.join(ROOT, "data_export")

_LEVELS = {
    "Equities (S&P 500 TR)": None,  # no absolute level in this fetcher, return-only
    "Gold": fcl.gold_price,
    "Silver (derived)": fcl.silver_price_derived,
    "Copper (PPI index)": fcl.copper_ppi_index,
    "Oil (WTI-era)": fcl.oil_price,
}


def _master_long(tagged: pd.DataFrame) -> pd.DataFrame:
    assets = [c for c in tagged.columns if c != "regime"]
    rows = []
    for asset in assets:
        ret = tagged[asset]
        vol = ret.rolling(5, min_periods=3).std()
        level_fn = _LEVELS.get(asset)
        level = level_fn().reindex(tagged.index) if level_fn is not None else pd.Series(
            index=tagged.index, dtype=float)
        for date in tagged.index:
            if pd.isna(ret.loc[date]) and pd.isna(level.loc[date]):
                continue
            rows.append({
                "date": date.date().isoformat(), "asset": asset,
                "price": level.loc[date] if pd.notna(level.loc[date]) else None,
                "return": ret.loc[date] if pd.notna(ret.loc[date]) else None,
                "vol_5yr": vol.loc[date] if pd.notna(vol.loc[date]) else None,
                "regime": tagged["regime"].loc[date],
            })
    return pd.DataFrame(rows)


def build_export() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    returns = rs.build_returns()
    tagged = rs.attach_regime(returns)
    corrs = rs.correlation_matrices(tagged)
    return {
        "regime_study_master": _master_long(tagged),
        "regime_study_corr_full": corrs["full_period"],
        "regime_study_corr_recession": corrs["recession"],
        "regime_study_corr_expansion": corrs["expansion"],
        "regime_study_playbook": rs.regime_playbook(tagged),
        "regime_study_diagnostics": rs.diagnostic_snapshot(),
    }


_INDEXED = {"regime_study_corr_full", "regime_study_corr_recession", "regime_study_corr_expansion"}


def main():
    sheets = build_export()
    for name, df in sheets.items():
        p = os.path.join(OUT_DIR, f"{name}.csv")
        df.to_csv(p, index=(name in _INDEXED))
        print(f"  {name:28s} {df.shape}  -> {p}")


if __name__ == "__main__":
    main()
