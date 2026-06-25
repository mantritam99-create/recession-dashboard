"""Shared pytest hooks — skip FRED-dependent tests when no API key is configured."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import has_fred


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_fred: needs FRED_API_KEY or config.local.yaml (full indicator coverage)",
    )


def pytest_collection_modifyitems(config, items):
    if has_fred():
        return
    skip = pytest.mark.skip(
        reason="FRED API key required — set config.local.yaml or FRED_API_KEY env var"
    )
    for item in items:
        if item.get_closest_marker("requires_fred"):
            item.add_marker(skip)
