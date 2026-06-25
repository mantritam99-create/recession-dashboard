"""v2 baseline regression net (V3 Phase 0).

Locks the current scoring pipeline's output so later V3 phases cannot silently
change composite / bucket / tripwire / base-rate-probability behavior.

Strict on discrete fields (tripwire armed/not, prob bucket label); within-EPS on
floats. CAVEAT: the live value drifts as FRED/market data updates, and historical
as-of values can shift microscopically if FRED revises past data between cache
refetches. EPS absorbs that while still catching real code changes (a refactor
bug moves the composite by points, not tenths). Within a single refactor session
the 12h cache keeps inputs fixed, so this is a tight net for Phases 1-3.

Regenerate the fixture:  py tests/test_baseline_snapshot.py
Run the test:            py -m pytest tests/test_baseline_snapshot.py
"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from model import indicators, scoring, analytics
from output import verdict

SNAP = os.path.join(os.path.dirname(__file__), "snapshots", "v2_baseline.json")
EPS = 0.5

# 4 historical as-of dates + the live read. Stretched pick = 2024-12: high
# valuation but quiet macro/credit ("expensive + calm"), the regime the whole
# dashboard exists to distinguish from genuine pre-recession stress.
ASOF_DATES = {
    "dotcom_2000_03": "2000-03-31",
    "gfc_2007_10": "2007-10-31",
    "covid_2020_03": "2020-03-31",
    "stretched_2024_12": "2024-12-31",
}


def compute_snapshot() -> dict:
    """Capture the current pipeline's output: live full state + historical as-of composites."""
    loaded = indicators.load_all()
    rows = indicators.compute(loaded)
    c = scoring.composite(rows)
    a = verdict.assess(rows, c)
    probs = analytics.probabilities(loaded)
    live = {
        "composite": c["composite"],
        "buckets": c["bucket"],
        "tripped": a["tripped"],
        "tripwires": {tw["name"]: {"armed": bool(t), "value": v} for t, tw, v in a["tripwires"]},
        "prob_bucket": probs.get("bucket"),
        "prob_recession": probs.get("recession"),
    }
    asof = {}
    for key, d in ASOF_DATES.items():
        r = scoring.composite_asof(loaded, pd.Timestamp(d))
        asof[key] = {"composite": r["composite"], "buckets": r["bucket"]}
    return {"live": live, "asof": asof}


def _close(a, b) -> bool:
    if a is None and b is None:
        return True
    return a is not None and b is not None and abs(a - b) <= EPS


@pytest.mark.requires_fred
def test_baseline_snapshot():
    assert os.path.exists(SNAP), f"fixture missing — run: py {__file__}"
    with open(SNAP, encoding="utf-8") as f:
        base = json.load(f)
    cur = compute_snapshot()

    # live composite (float, EPS)
    assert _close(cur["live"]["composite"], base["live"]["composite"]), \
        f'live composite {cur["live"]["composite"]} vs baseline {base["live"]["composite"]}'

    # tripwire armed states (discrete, exact) + count
    assert cur["live"]["tripped"] == base["live"]["tripped"], "tripped count changed"
    for name, d in base["live"]["tripwires"].items():
        assert cur["live"]["tripwires"][name]["armed"] == d["armed"], f"tripwire {name} armed-state changed"

    # base-rate probability bucket label (discrete) + recession prob (EPS)
    assert cur["live"]["prob_bucket"] == base["live"]["prob_bucket"], "prob bucket label changed"
    assert _close(cur["live"]["prob_recession"], base["live"]["prob_recession"]), "recession prob changed"

    # historical as-of composites (float, EPS) — locks the causal trajectory
    for key in base["asof"]:
        assert _close(cur["asof"][key]["composite"], base["asof"][key]["composite"]), \
            f'{key} composite {cur["asof"][key]["composite"]} vs baseline {base["asof"][key]["composite"]}'


if __name__ == "__main__":
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    snap = compute_snapshot()
    with open(SNAP, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2)
    print("wrote", SNAP)
    print(json.dumps(snap, indent=2)[:1200])
