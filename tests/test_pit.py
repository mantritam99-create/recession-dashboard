"""Point-in-time integrity lock (V3 Phase 1).

Phase 0 found historical scoring is already causal: indicators.percentile_asof
slices `series[series.index <= asof]` before ranking. This test FREEZES that
property so no later refactor can silently introduce look-ahead — appending
future data must not change a past as-of score.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from model import indicators


def test_percentile_asof_is_causal():
    idx = pd.date_range("1990-01-31", periods=200, freq="ME")
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(size=200).cumsum(), index=idx)
    asof = idx[120]

    # score using only data up to `asof`
    _, score_now = indicators.percentile_asof(s, asof, "high")

    # append wildly different FUTURE data, recompute the SAME as-of score
    future = pd.Series(rng.normal(loc=50, size=80).cumsum() + 999,
                       index=pd.date_range(idx[-1] + pd.offsets.MonthEnd(), periods=80, freq="ME"))
    s2 = pd.concat([s, future])
    _, score_after = indicators.percentile_asof(s2, asof, "high")

    assert score_now == score_after, f"look-ahead leak: {score_now} != {score_after}"


def test_stats_utils_rolling_zscore_causal():
    """Shared helper's PIT z-score at date t must not move when future data is appended."""
    import stats_utils as su
    idx = pd.date_range("2000-01-31", periods=100, freq="ME")
    s = pd.Series(np.arange(100.0), index=idx)
    z_full = su.rolling_zscore(s, 24, su.PIT)
    z_trunc = su.rolling_zscore(s.iloc[:60], 24, su.PIT)
    # the value at position 59 uses only the trailing window -> identical either way
    assert abs(z_full.iloc[59] - z_trunc.iloc[59]) < 1e-9
