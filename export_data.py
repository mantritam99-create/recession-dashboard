"""Consolidated data export — "the entire data file" for the project.

Pulls everything the dashboard uses into ONE place so it can be handed in / inspected
without running the pipeline:
  - catalog            : every indicator (name, source, bucket, direction)
  - feature_catalog    : the 31-feature registry (name, family, transform, ...)
  - raw_monthly        : all raw series, month-end, wide (date x indicator)
  - features           : the computed 31-feature matrix (month-end)
  - composite_history  : monthly composite + regime bucket, 1999-2026
  - bubble_scorecard   : bucket stress at past episodes (dot-com/GFC/COVID/now)
  - transition_3m/6m   : Markov regime-transition matrices

Writes a single Excel workbook if a writer is available, else one CSV per sheet.

Run:  py export_data.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

from config import CFG, ROOT
from model import indicators, scoring, analytics
import features as feat

OUT_DIR = os.path.join(ROOT, "data_export")
XLSX = os.path.join(OUT_DIR, "recession_dashboard_data.xlsx")


def _catalog() -> pd.DataFrame:
    rows = []
    for sid, m in CFG["fred_series"].items():
        rows.append({"id": sid, "name": m["name"], "source": "FRED", "bucket": m["bucket"],
                     "direction": m["direction"]})
    for tkr, m in CFG["market_tickers"].items():
        rows.append({"id": tkr, "name": m["name"], "source": "Yahoo", "bucket": m["bucket"],
                     "direction": m["direction"]})
    for k, m in CFG["valuation"].items():
        rows.append({"id": k, "name": m["name"], "source": m.get("source", "computed"),
                     "bucket": m["bucket"], "direction": m["direction"]})
    return pd.DataFrame(rows)


def _feature_catalog() -> pd.DataFrame:
    return pd.DataFrame([fd.__dict__ for fd in feat.FEATURE_REGISTRY])


def _raw_monthly(raw: dict) -> pd.DataFrame:
    cols = {k: v.dropna().resample("ME").last() for k, v in raw.items() if v is not None and not v.dropna().empty}
    return pd.DataFrame(cols).sort_index()


def _composite_history(loaded) -> pd.DataFrame:
    comp = analytics.composite_series(loaded, start="1999-01-01")
    df = pd.DataFrame(comp, columns=["date", "composite"])
    df["bucket"] = df["composite"].map(
        lambda v: analytics.REGIME_LABELS[analytics.regime_bucket(v)] if analytics.regime_bucket(v) is not None else None)
    return df


def _scorecard(loaded) -> pd.DataFrame:
    rows = []
    for h in analytics.historical_scorecard(loaded):
        r = {"episode": h["episode"], "stage": h["stage"], "date": h["date"],
             "composite": h["composite"], "n_live": h["n_live"]}
        r.update(h["buckets"])
        rows.append(r)
    return pd.DataFrame(rows)


def build_export() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    loaded = indicators.load_all()
    raw = indicators.load_raw_data()
    bs = analytics.bucket_series_monthly(loaded)
    mats = analytics.compute_transition_matrix(bs, horizons=(3, 6))
    sheets = {
        "catalog": _catalog(),
        "feature_catalog": _feature_catalog(),
        "raw_monthly": _raw_monthly(raw),
        "features": feat.compute_features(raw),
        "composite_history": _composite_history(loaded),
        "bubble_scorecard": _scorecard(loaded),
        "transition_3m": (mats[3] * 100).round(1),
        "transition_6m": (mats[6] * 100).round(1),
    }
    return sheets


# index=True only for the time-indexed / matrix sheets
_INDEXED = {"raw_monthly", "features", "transition_3m", "transition_6m"}


def main():
    sheets = build_export()
    try:
        with pd.ExcelWriter(XLSX) as xl:
            for name, df in sheets.items():
                df.to_excel(xl, sheet_name=name[:31], index=(name in _INDEXED))
        print("wrote", XLSX)
    except Exception as e:  # no Excel engine -> CSV fallback
        print(f"  (no Excel writer: {e}; writing CSVs instead)")
        for name, df in sheets.items():
            p = os.path.join(OUT_DIR, f"{name}.csv")
            df.to_csv(p, index=(name in _INDEXED))
            print("wrote", p)
    for name, df in sheets.items():
        print(f"  {name:18s} {df.shape}")


if __name__ == "__main__":
    main()
