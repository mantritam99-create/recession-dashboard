"""Shared causal stats helpers (V3 Phase 1).

THE single home for rolling/z-score/YoY/standardization logic. Every later phase
(features, factors) must call these instead of reimplementing — so causal vs
full-sample is an explicit, auditable choice, never silently chosen.

`Mode.point_in_time=True`  -> causal: at each date t use only data <= t (rolling /
                             expanding). Use for backtests / historical scoring.
`Mode.point_in_time=False` -> full-sample: use the whole series' stats. Use only
                             for live display, where lookahead is irrelevant.
"""
from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class Mode:
    point_in_time: bool  # True = causal (backtest), False = full-sample (live)


PIT = Mode(point_in_time=True)
FULL = Mode(point_in_time=False)


def rolling_zscore(series: pd.Series, window: int, mode: Mode) -> pd.Series:
    """z-score of `series`. PIT: trailing rolling window (causal). Full: global mean/std."""
    s = series.astype(float)
    if mode.point_in_time:
        mean = s.rolling(window, min_periods=max(2, window // 2)).mean()
        std = s.rolling(window, min_periods=max(2, window // 2)).std()
        return (s - mean) / std.replace(0, pd.NA)
    mean, std = s.mean(), s.std()
    return (s - mean) / (std if std else pd.NA)


def pct_change_yoy(series: pd.Series, mode: Mode) -> pd.Series:
    """Year-over-year % change, frequency-agnostic and causal regardless of mode:
    align each date to the last observation on/before one year earlier."""
    s = series.astype(float).dropna()
    prior = s.reindex(s.index - pd.DateOffset(years=1), method="ffill")
    prior.index = s.index
    out = s / prior - 1.0
    return out.reindex(series.index)  # mode kept for API symmetry; YoY is inherently backward-looking


def standardize_features(df: pd.DataFrame, mode: Mode) -> pd.DataFrame:
    """Per-column standardization. PIT: expanding (causal). Full: global mean/std."""
    x = df.astype(float)
    if mode.point_in_time:
        mean = x.expanding(min_periods=12).mean()
        std = x.expanding(min_periods=12).std()
    else:
        mean, std = x.mean(), x.std()
    return (x - mean) / std.where(std != 0, other=pd.NA)


def _demo():
    import numpy as np
    idx = pd.date_range("2000-01-31", periods=60, freq="ME")
    s = pd.Series(np.arange(60.0), index=idx)
    z = rolling_zscore(s, 12, PIT)
    assert pd.notna(z.iloc[-1])                      # causal z-score finite at the last point
    y = pct_change_yoy(s + 1, FULL)                  # +1 so the year-ago denominator is nonzero
    assert y.notna().sum() > 0
    st = standardize_features(s.to_frame("x"), FULL)
    assert abs(st["x"].mean()) < 1e-9                # full-sample standardize -> mean ~0
    print("[stats_utils] demo OK")


if __name__ == "__main__":
    _demo()
