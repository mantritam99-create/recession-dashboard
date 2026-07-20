"""Long-run (annual, up to ~100yr) equity/commodity/regime data for the regime study.

Separate from fetch_fred.py / fetch_market.py, which are tuned for live daily/monthly
indicators. These sources update once a year at most, so each puller here does its own
download+parse and leans on cache_util the same way (get-or-build-or-degrade-to-stale),
just reusing the existing monthly_max_age_h cache tier rather than adding a new config
knob for data that barely changes.

Sources (all real, no fabricated figures):
- Damodaran/NYU Stern histretSP.xls: S&P 500 total return, gold $/oz (1927-2025).
- MeasuringWorth gold/silver dataset (POST form, public): NY gold price + gold/silver
  ratio (1687-2025) -> silver derived as ny_gold / ratio. USGS Data Series 140 and
  Macrotrends -- the "obvious" silver sources -- both return WAF/Cloudflare bot
  challenges to curl and to a headless browser; this sidesteps them entirely.
- FRED WPU102502 (PPI: Copper and Brass Mill Shapes, Dec 1953-present) via fetch_fred:
  a producer-price *index*, not a $/lb spot price -- treat as growth-of-100, same as
  the bond/bill legs in the Phase 0 dataset.
- EIA T09.01 (Crude Oil Domestic First Purchase Price, 1949-present).
- FRED USREC (NBER recession dummy, monthly 0/1) -> annual regime label.
"""
import os, sys, csv, io, re, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import cache_util as cache
from config import CFG
from data import fetch_fred

_HDR = {"User-Agent": "Mozilla/5.0"}
_MAX = CFG["cache"]["monthly_max_age_h"]

_DAMODARAN_XLS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/histretSP.xls"
_EIA_OIL_CSV = "https://www.eia.gov/totalenergy/data/browser/csv.php?tbl=T09.01"
_MW_GOLD_URL = "https://www.measuringworth.com/datasets/gold/result.php"

_wb_cache: dict = {}


def _annual_index(years):
    return pd.to_datetime([f"{int(y)}-01-01" for y in years])


def _clip(s, start):
    return s[s.index.year >= start] if s is not None else None


def _cached_annual(key: str, build):
    """Shared fetch-or-cache-or-degrade contract, same shape as fetch_fred.series()."""
    s = cache.get_series(key, _MAX)
    if s is not None:
        return s
    try:
        s = build()
        return cache.put_series(key, s)
    except Exception as e:
        print(f"  [commodities_long] {key} failed: {e.__class__.__name__}: {str(e)[:80]}")
        return cache.get_series(key, 1e9)  # any age


def _damodaran_wb():
    if "wb" not in _wb_cache:
        import xlrd
        req = urllib.request.Request(_DAMODARAN_XLS, headers=_HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        _wb_cache["wb"] = xlrd.open_workbook(file_contents=data)
    return _wb_cache["wb"]


def _build_sp500_total_return():
    sheet = _damodaran_wb().sheet_by_name("S&P 500 & Raw Data")
    rows = {}
    for r in range(2, sheet.nrows):
        row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        if row[0] == "":
            continue
        rows[int(row[0])] = row
    years = sorted(rows)
    rets = {}
    for i in range(1, len(years)):
        y0, y1 = years[i - 1], years[i]
        p0, p1 = rows[y0][1], rows[y1][1]
        dy = rows[y1][3] if rows[y1][3] != "" else 0.0
        rets[y1] = (p1 - p0) / p0 + dy
    s = pd.Series(rets).sort_index()
    s.index = _annual_index(s.index)
    return s


def _build_gold_price():
    sheet = _damodaran_wb().sheet_by_name("Gold Prices")
    rows = {}
    for r in range(1, sheet.nrows):
        y, v = sheet.cell_value(r, 0), sheet.cell_value(r, 1)
        if y == "":
            continue
        rows[int(y)] = v
    s = pd.Series(rows).sort_index()
    s.index = _annual_index(s.index)
    return s


def _build_measuringworth():
    """Year -> (ny_gold_usd_per_oz, gold_silver_ratio) from the public dataset form."""
    body = urllib.parse.urlencode({
        "london": "on", "goldsilver": "on", "newyork": "on",
        "year_source": "1687", "year_result": "2025",
    }).encode()
    req = urllib.request.Request(_MW_GOLD_URL, data=body, headers=_HDR, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    rows = re.findall(
        r"<tr><td>(\d{4})</td><td>([^<]*)</td><td>([^<]*)</td><td>[^<]*</td></tr>", html)
    out = {}
    for yr, ny, ratio in rows:
        ny = ny.replace(",", "").strip()
        ratio = ratio.replace(",", "").strip()
        if ny and ratio:
            out[int(yr)] = (float(ny), float(ratio))
    return out


def _build_silver_derived():
    mw = _build_measuringworth()
    rows = {y: ny / ratio for y, (ny, ratio) in mw.items() if ratio}
    s = pd.Series(rows).sort_index()
    s.index = _annual_index(s.index)
    return s


def _build_copper_ppi():
    s = fetch_fred.series("WPU102502", start="1953-01-01")
    if s is None:
        raise RuntimeError("FRED WPU102502 unavailable (no key configured or fetch failed)")
    return s.resample("YS").mean()


def _build_oil_price():
    req = urllib.request.Request(_EIA_OIL_CSV, headers=_HDR)
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    reader = csv.reader(io.StringIO(text))
    next(reader)
    rows = {}
    for row in reader:
        if len(row) < 3:
            continue
        msn, yyyymm, val = row[0], row[1], row[2]
        if msn == "CODPUUS" and yyyymm.endswith("13"):
            try:
                rows[int(yyyymm[:4])] = float(val)
            except ValueError:
                pass
    s = pd.Series(rows).sort_index()
    s.index = _annual_index(s.index)
    return s


def _build_recession_regime():
    """NBER USREC (monthly 0/1) -> annual label: 'recession' if >=half the year's
    months were in recession, else 'expansion'."""
    s = fetch_fred.series("USREC", start="1926-01-01")
    if s is None:
        raise RuntimeError("FRED USREC unavailable (no key configured or fetch failed)")
    frac = s.resample("YS").mean()
    return frac.apply(lambda f: "recession" if f >= 0.5 else "expansion")


# ---- public API ----

def sp500_total_return(start: int = 1928):
    return _clip(_cached_annual("long_sp500_total_return", _build_sp500_total_return), start)


def gold_price(start: int = 1927):
    return _clip(_cached_annual("long_gold_price", _build_gold_price), start)


def silver_price_derived(start: int = 1687):
    return _clip(_cached_annual("long_silver_derived", _build_silver_derived), start)


def copper_ppi_index(start: int = 1953):
    return _clip(_cached_annual("long_copper_ppi", _build_copper_ppi), start)


def oil_price(start: int = 1949):
    return _clip(_cached_annual("long_oil_price", _build_oil_price), start)


def recession_regime(start: int = 1926):
    return _clip(_cached_annual("long_recession_regime", _build_recession_regime), start)


if __name__ == "__main__":
    for name, fn in [
        ("S&P500 total return", sp500_total_return),
        ("Gold $/oz", gold_price),
        ("Silver $/oz (derived)", silver_price_derived),
        ("Copper PPI index", copper_ppi_index),
        ("Oil $/bbl", oil_price),
        ("NBER regime", recession_regime),
    ]:
        s = fn()
        tag = f"n={len(s)} last={s.iloc[-1]}" if s is not None and len(s) else "None"
        print(f"{name:24s} -> {tag}")
