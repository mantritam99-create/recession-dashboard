"""Valuation inputs.

CAPE: scraped from multpl.com's by-month history table (keyless) -> full monthly
      series back to 1881, so percentile ranking is against true history.
Buffett Indicator: computed = Wilshire 5000 / GDP (needs FRED key). We OWN the
      formula rather than trusting a third party; flagged for calibration.
"""
import os, sys, re, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cache_util as cache
from data import fetch_fred

_HDR = {"User-Agent": "Mozilla/5.0"}
_MAX = 720  # monthly cadence

_ROW = re.compile(
    r"<td[^>]*>\s*([A-Z][a-z]{2,8}\s+\d{1,2},\s*\d{4})\s*</td>\s*"
    r"<td[^>]*>\s*([\d.]+)", re.S)


def cape_history() -> pd.Series | None:
    """Monthly Shiller CAPE series (newest-last), scraped from multpl.com."""
    key = "val_cape_hist"
    s = cache.get_series(key, _MAX)
    if s is not None:
        return s
    try:
        req = urllib.request.Request(
            "https://www.multpl.com/shiller-pe/table/by-month", headers=_HDR)
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "replace")
        # multpl pads the value cell with &#x2002; (an entity that itself contains
        # "2002") — strip all HTML entities first so they can't poison the number match
        html = re.sub(r"&#?\w+;", " ", html)
        rows = _ROW.findall(html)
        if not rows:
            print("  [valuation] CAPE table parse found 0 rows")
            return None
        idx = pd.to_datetime([d for d, _ in rows])
        s = pd.Series([float(v) for _, v in rows], index=idx).sort_index()
        return cache.put_series(key, s)
    except Exception as e:
        print(f"  [valuation] CAPE failed: {e.__class__.__name__}: {str(e)[:80]}")
        return cache.get_series(key, 1e9)


def buffett_history() -> pd.Series | None:
    """Buffett Indicator = corporate equities / GDP, %, quarterly. Needs FRED key.

    FRED discontinued the Wilshire 5000 series, so we use NCBEILQ027S (Nonfinancial
    Corporate Business; Corporate Equities; Liability, $M) as the market-value
    numerator — the standard replacement, with history back to 1945.
    """
    eq = fetch_fred.series("NCBEILQ027S")    # market value of equities, $Millions, quarterly
    gdp = fetch_fred.series("GDP")           # nominal GDP, $Billions, quarterly
    if eq is None or gdp is None:
        return None
    df = pd.concat([eq, gdp], axis=1).dropna()
    return (df.iloc[:, 0] / 1000.0 / df.iloc[:, 1] * 100.0).dropna()  # ($B equities / $B GDP) * 100


if __name__ == "__main__":
    c = cape_history()
    if c is not None:
        print(f"CAPE: n={len(c)} range={c.index.min().date()}..{c.index.max().date()} "
              f"current={c.iloc[-1]:.2f}")
