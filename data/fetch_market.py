"""Market data via Yahoo's chart endpoint directly (keyless, ~0.4s).

We hit query1.finance.yahoo.com instead of the yfinance wrapper: it's the exact
same data source yfinance uses, minus a fragile dependency. Cached per ticker.
Degrades to the last cached pull (any age) if Yahoo is unreachable.
"""
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cache_util as cache
from config import CFG

_HDR = {"User-Agent": "Mozilla/5.0"}
_MAX = CFG["cache"]["market_max_age_h"]


def _get(url: str):
    req = urllib.request.Request(url, headers=_HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def history(ticker: str, range_: str = "max", interval: str = "1d") -> pd.Series | None:
    """Date-indexed close-price series. Cached; falls back to stale cache offline."""
    key = f"mkt_{ticker}_{range_}_{interval}"
    s = cache.get_series(key, _MAX)
    if s is not None:
        return s
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?range={range_}&interval={interval}")
    try:
        d = _get(url)
        res = d["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
        s = pd.Series(closes, index=pd.to_datetime(ts, unit="s")).dropna()
        s.index = s.index.normalize()
        return cache.put_series(key, s)
    except Exception as e:
        stale = cache.get_series(key, 1e9)  # any age
        print(f"  [market] {ticker} fetch failed ({e.__class__.__name__}); "
              f"{'using stale cache' if stale is not None else 'no cache'}")
        return stale


def latest(ticker: str) -> float | None:
    s = history(ticker, range_="1y")
    return float(s.iloc[-1]) if s is not None and len(s) else None


if __name__ == "__main__":
    for t in ["^GSPC", "^VIX", "^TNX", "NVDA"]:
        s = history(t)
        print(f"{t:10s} last={latest(t):>10.2f}  n={len(s) if s is not None else 0}")
