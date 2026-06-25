"""Feature registry sanity (V3 Phase 2).

Checks the registry computes cleanly off real cached data: expected columns,
no broken raw_id mappings (all-NaN columns), and live coverage in recent months.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model import indicators
import features


@pytest.mark.requires_fred
def test_features_compute():
    raw = indicators.load_raw_data()
    df = features.compute_features(raw)
    names = {fd.name for fd in features.FEATURE_REGISTRY}

    assert not df.empty, "no features computed"
    assert set(df.columns) <= names, "unexpected columns vs registry"
    # allow at most a few skipped (e.g. a series unavailable without a FRED key)
    assert df.shape[1] >= len(names) - 4, f"too many features missing: {names - set(df.columns)}"

    # no column entirely NaN -> would mean a broken raw_id mapping
    all_nan = [c for c in df.columns if df[c].notna().sum() == 0]
    assert not all_nan, f"all-NaN features (bad raw_id?): {all_nan}"

    # recent coverage: most features have a value in the last 3 months
    recent_cov = (df.tail(3).notna().any()).mean()
    assert recent_cov > 0.6, f"weak recent coverage: {recent_cov:.2f}"


def test_registry_families_present():
    fams = set(features.registry_by_family())
    assert {"growth", "labor", "inflation", "credit", "liquidity", "valuation", "sentiment"} <= fams
