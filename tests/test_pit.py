"""Historical integrity locks: date causality and revision-policy enforcement.

Phase 0 found historical scoring is already causal: indicators.percentile_asof
slices `series[series.index <= asof]` before ranking. This test FREEZES that
property so no later refactor can silently introduce look-ahead. Separate tests
make explicit that date causality alone is not vintage correctness.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
import pytest
from model import backtest, indicators


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


def test_date_causality_is_not_vintage_correctness():
    """A revised past observation can change a past score without any future rows."""
    idx = pd.date_range("2000-01-31", periods=60, freq="ME")
    original = pd.Series(np.arange(60.0), index=idx)
    revised = original.copy()
    revised.iloc[-1] = -100.0

    _, original_score = indicators.percentile_asof(original, idx[-1], "high")
    _, revised_score = indicators.percentile_asof(revised, idx[-1], "high")

    assert original_score != revised_score


def test_revision_policy_delays_revision_prone_series():
    idx = pd.date_range("2020-01-31", periods=3, freq="ME")
    original = pd.Series([1.0, 2.0, 3.0], index=idx)
    delayed = indicators.apply_revision_policy(original, "ICSA")

    assert delayed.index[0] == pd.Timestamp("2020-02-29")
    assert delayed.index[-1] == pd.Timestamp("2020-04-30")


def test_every_loaded_series_has_a_revision_classification():
    configured = indicators.CFG["revisions_policy"]["series"]
    valid = {"revision_safe", "revision_prone", "unavailable_vintage"}
    for spec in indicators._specs():
        assert spec["key"] in configured
        assert configured[spec["key"]]["classification"] in valid


def test_backtest_rejects_incomplete_scored_history():
    spec = {"name": "Missing", "bucket": "credit"}
    with pytest.raises(RuntimeError, match="complete scored-series history"):
        backtest._require_complete([(spec, None)])


def test_stats_utils_rolling_zscore_causal():
    """Shared helper's PIT z-score at date t must not move when future data is appended."""
    import stats_utils as su
    idx = pd.date_range("2000-01-31", periods=100, freq="ME")
    s = pd.Series(np.arange(100.0), index=idx)
    z_full = su.rolling_zscore(s, 24, su.PIT)
    z_trunc = su.rolling_zscore(s.iloc[:60], 24, su.PIT)
    # the value at position 59 uses only the trailing window -> identical either way
    assert abs(z_full.iloc[59] - z_trunc.iloc[59]) < 1e-9
