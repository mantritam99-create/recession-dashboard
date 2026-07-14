"""FRED via the official API (api.stlouisfed.org). Requires a free key.

The keyless fredgraph CSV subdomain is firewalled in some environments (it timed
out here), so we use the authenticated JSON API. With no key configured, every
call returns None and the model flags reduced confidence — it never crashes.
"""
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cache_util as cache
from config import CFG, fred_key, has_fred

_HDR = {"User-Agent": "Mozilla/5.0"}
_START = CFG["fred"]["start"]
_MAX = CFG["cache"]["monthly_max_age_h"]  # FRED publishes on a lag; daily is fine
_warned = False


def series(series_id: str, start: str | None = None,
           allow_stale: bool = False) -> pd.Series | None:
    global _warned
    key = f"fred_{series_id}"
    s = cache.get_series(key, _MAX)
    if s is not None:
        return s

    if not has_fred():
        stale = cache.get_series(key, 1e9) if allow_stale else None
        if not _warned:
            action = "using stale cache" if stale is not None else "FRED indicators skipped"
            print("  [fred] no API key (config.yaml fred.api_key or $FRED_API_KEY) "
                  f"-> {action}")
            _warned = True
        return stale

    q = urllib.parse.urlencode({
        "series_id": series_id, "api_key": fred_key(), "file_type": "json",
        "observation_start": start or _START,
    })
    url = f"https://api.stlouisfed.org/fred/series/observations?{q}"
    try:
        req = urllib.request.Request(url, headers=_HDR)
        with urllib.request.urlopen(req, timeout=25) as r:
            obs = json.loads(r.read().decode("utf-8"))["observations"]
        idx = pd.to_datetime([o["date"] for o in obs])
        vals = pd.to_numeric(pd.Series([o["value"] for o in obs], index=idx),
                             errors="coerce").dropna()
        return cache.put_series(key, vals)
    except Exception as e:
        print(f"  [fred] {series_id} failed: {e.__class__.__name__}: {str(e)[:80]}")
        return cache.get_series(key, 1e9)


def yoy(s: pd.Series) -> pd.Series:
    """Year-over-year % change for level series (e.g. core CPI index -> YoY %)."""
    return (s / s.shift(12) - 1.0).dropna() * 100 if s is not None else None


if __name__ == "__main__":
    for sid in ["DGS10", "T10Y3M", "BAMLH0A0HYM2", "SAHMREALTIME"]:
        s = series(sid)
        print(f"{sid:14s} -> {('n=%d last=%.3f' % (len(s), s.iloc[-1])) if s is not None else 'None'}")
