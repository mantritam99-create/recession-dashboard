"""Feature registry (V3 Phase 2, minimum viable feature-store-lite).

Turns the ~19 existing raw series into a compact, explicit set of derived
features. NOT wired into the live composite — runs side-by-side and inspectable,
so it can be validated before anything depends on it (Phase 4 factors will).

All rolling/z-score/YoY math goes through `stats_utils` (the shared causal
helper) — no reimplementation here. Discipline: prefer FEWER, more independent
features. We do NOT add both a 4w and 13w MA on an already-smooth monthly series;
for trending series we use YoY (stationary) rather than a level z-score (which
just tracks the trend). Comments note skipped transforms and why.
"""
from dataclasses import dataclass

import pandas as pd

import stats_utils as su

ZWIN = 60  # 5y rolling window for monthly z-scores


@dataclass(frozen=True)
class FeatureDef:
    name: str
    raw_id: str            # key into indicators.load_raw_data()
    family: str            # growth | labor | inflation | credit | liquidity | valuation | sentiment
    transform: str         # level | zscore | yoy | yoy_z | diff
    frequency: str         # native cadence of the raw series
    source: str
    confidence: float      # 0.5–0.9 subjective data-quality
    used_in_composite: bool  # is the parent indicator in the v2 scored composite?


# One registry entry per (raw series, transform). raw_id must match
# indicators.load_raw_data() keys (FRED codes / tickers / 'cape' / 'buffett').
FEATURE_REGISTRY: list[FeatureDef] = [
    # --- growth (yield curve = recession lead; equity trend) ---
    FeatureDef("curve_3m10y_level", "T10Y3M", "growth", "level", "daily", "FRED:T10Y3M", 0.9, True),
    FeatureDef("curve_3m10y_z", "T10Y3M", "growth", "zscore", "daily", "FRED:T10Y3M", 0.9, False),
    FeatureDef("curve_2s10s_level", "T10Y2Y", "growth", "level", "daily", "FRED:T10Y2Y", 0.8, False),  # 2s10s confirmation-only; skip its z (corr w/ 3m10y)
    FeatureDef("spx_yoy", "^GSPC", "growth", "yoy", "daily", "YF:^GSPC", 0.7, False),
    FeatureDef("spx_yoy_z", "^GSPC", "growth", "yoy_z", "daily", "YF:^GSPC", 0.7, False),
    # --- labor (the spark) ---
    FeatureDef("sahm_level", "SAHMREALTIME", "labor", "level", "monthly", "FRED:SAHMREALTIME", 0.9, True),
    FeatureDef("sahm_z", "SAHMREALTIME", "labor", "zscore", "monthly", "FRED:SAHMREALTIME", 0.85, False),
    FeatureDef("claims_level", "ICSA", "labor", "level", "weekly", "FRED:ICSA", 0.85, True),
    FeatureDef("claims_yoy", "ICSA", "labor", "yoy", "weekly", "FRED:ICSA", 0.8, False),  # yoy > 4w MA here (zscore already smooths)
    # --- inflation (trending levels -> use YoY, not level z) ---
    FeatureDef("cpi_yoy", "CPILFESL", "inflation", "yoy", "monthly", "FRED:CPILFESL", 0.9, True),
    FeatureDef("cpi_yoy_z", "CPILFESL", "inflation", "yoy_z", "monthly", "FRED:CPILFESL", 0.8, False),
    FeatureDef("wti_yoy", "DCOILWTICO", "inflation", "yoy", "daily", "FRED:DCOILWTICO", 0.7, True),
    # --- credit (the spark; richest family) ---
    FeatureDef("hy_oas_level", "BAMLH0A0HYM2", "credit", "level", "daily", "FRED:BAMLH0A0HYM2", 0.9, True),
    FeatureDef("hy_oas_z", "BAMLH0A0HYM2", "credit", "zscore", "daily", "FRED:BAMLH0A0HYM2", 0.9, False),
    FeatureDef("ig_oas_level", "BAMLC0A0CM", "credit", "level", "daily", "FRED:BAMLC0A0CM", 0.85, True),
    FeatureDef("ig_oas_z", "BAMLC0A0CM", "credit", "zscore", "daily", "FRED:BAMLC0A0CM", 0.85, False),
    FeatureDef("bank_standards_level", "DRTSCILM", "credit", "level", "quarterly", "FRED:DRTSCILM", 0.8, True),
    FeatureDef("cc_delinq_level", "DRCCLACBS", "credit", "level", "quarterly", "FRED:DRCCLACBS", 0.8, True),
    FeatureDef("cc_delinq_z", "DRCCLACBS", "credit", "zscore", "quarterly", "FRED:DRCCLACBS", 0.75, False),
    # --- liquidity / financial conditions ---
    FeatureDef("vix_level", "^VIX", "liquidity", "level", "daily", "YF:^VIX", 0.85, True),
    FeatureDef("vix_z", "^VIX", "liquidity", "zscore", "daily", "YF:^VIX", 0.85, False),
    FeatureDef("tnx_level", "^TNX", "liquidity", "level", "daily", "YF:^TNX", 0.7, False),
    FeatureDef("dxy_yoy", "DX-Y.NYB", "liquidity", "yoy", "daily", "YF:DX-Y.NYB", 0.65, False),
    # --- valuation (the fuel) ---
    FeatureDef("cape_level", "cape", "valuation", "level", "monthly", "multpl:CAPE", 0.9, True),
    FeatureDef("cape_z", "cape", "valuation", "zscore", "monthly", "multpl:CAPE", 0.85, False),
    FeatureDef("buffett_level", "buffett", "valuation", "level", "quarterly", "FRED:computed", 0.8, True),
    FeatureDef("buffett_z", "buffett", "valuation", "zscore", "quarterly", "FRED:computed", 0.75, False),
    # --- sentiment ---
    FeatureDef("umich_level", "UMCSENT", "sentiment", "level", "monthly", "FRED:UMCSENT", 0.8, True),
    FeatureDef("umich_z", "UMCSENT", "sentiment", "zscore", "monthly", "FRED:UMCSENT", 0.75, False),
    FeatureDef("psavert_level", "PSAVERT", "sentiment", "level", "monthly", "FRED:PSAVERT", 0.7, True),
    FeatureDef("nvda_yoy", "NVDA", "sentiment", "yoy", "daily", "YF:NVDA", 0.6, False),
]


def _apply(transform: str, m: pd.Series, mode: su.Mode) -> pd.Series:
    """Apply one transform to an already-monthly series via the shared causal helper."""
    if transform == "level":
        return m
    if transform == "diff":
        return m.diff()
    if transform == "yoy":
        return su.pct_change_yoy(m, mode)
    if transform == "yoy_z":
        return su.rolling_zscore(su.pct_change_yoy(m, mode), ZWIN, mode)
    if transform == "zscore":
        return su.rolling_zscore(m, ZWIN, mode)
    raise ValueError(f"unknown transform {transform!r}")


def compute_features(raw_data: dict[str, pd.Series], mode: su.Mode = su.FULL,
                     freq: str = "ME") -> pd.DataFrame:
    """raw_id -> series  ==>  wide monthly feature DataFrame (one column per FeatureDef).

    Resamples every raw series to month-END first (the Phase 0 aggregation convention)
    so cross-frequency series share one grid, then applies each feature's transform.
    `mode` defaults to FULL (live); pass su.PIT for causal/backtest use.
    """
    cols: dict[str, pd.Series] = {}
    for fd in FEATURE_REGISTRY:
        s = raw_data.get(fd.raw_id)
        if s is None or s.dropna().empty:
            continue  # series unavailable (e.g. no FRED key) — skip, don't crash
        # month-end last; ffill(limit=3) carries quarterly series (bank standards,
        # cc delinquency, Buffett) across their 2 empty intra-quarter months. Causal.
        monthly = s.dropna().resample(freq).last().ffill(limit=3)
        cols[fd.name] = _apply(fd.transform, monthly, mode)
    return pd.DataFrame(cols).sort_index()


def registry_by_family() -> dict[str, list[str]]:
    """feature names grouped by family — for the Phase 4 PCA-per-family layer."""
    out: dict[str, list[str]] = {}
    for fd in FEATURE_REGISTRY:
        out.setdefault(fd.family, []).append(fd.name)
    return out


if __name__ == "__main__":
    from model import indicators  # noqa: E402  (only when run directly, from repo root)
    raw = indicators.load_raw_data()
    df = compute_features(raw)
    print(f"{len(FEATURE_REGISTRY)} features defined, {df.shape[1]} computed, {df.shape[0]} months")
    print("families:", {k: len(v) for k, v in registry_by_family().items()})
    print(df.tail(2).T.to_string()[:1500])
