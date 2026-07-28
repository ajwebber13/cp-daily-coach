"""
sector_strength.py
"Strong stocks usually belong to strong sectors." Checks whether a
ticker's sector (via its matching SPDR sector ETF) is itself in an
uptrend. A stock can look great on its own but be swimming against a
weak sector — this flags that mismatch.

Uses the 11 standard GICS sectors mapped to their SPDR ETFs (XLK, XLF,
XLE, etc.) — the same reliable, liquid sector ETFs most traders already
watch.
"""
import pandas as pd

import config
from indicators import add_indicators
from scorer import trend_aligned

SECTOR_MAP_FILE = "sector_map.csv"

ALL_SECTOR_ETFS = ["XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLK", "XLB", "XLRE", "XLU"]


def load_sector_map() -> dict:
    """Returns {ticker: sector_etf}. Missing/unmapped tickers just get
    skipped later — the coach still works without full sector coverage."""
    try:
        df = pd.read_csv(SECTOR_MAP_FILE)
        return dict(zip(df["ticker"], df["sector_etf"]))
    except FileNotFoundError:
        print(f"{SECTOR_MAP_FILE} not found — sector strength will be skipped for all tickers.")
        return {}


def get_sector_trends() -> dict:
    """
    Downloads all 11 sector ETFs once and checks which are trending up.
    Returns {etf_ticker: bool}. On failure, returns an empty dict so the
    scan can proceed without sector data rather than crashing.
    """
    try:
        import yfinance as yf
        raw = yf.download(
            ALL_SECTOR_ETFS, period=f"{config.LOOKBACK_DAYS}d",
            group_by="ticker", auto_adjust=True, threads=True, progress=False,
        )

        trends = {}
        for etf in ALL_SECTOR_ETFS:
            try:
                df = raw[etf].rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
                if len(df) > config.SMA_TREND:
                    df = add_indicators(df)
                    trends[etf] = trend_aligned(df.iloc[-1])
            except Exception:
                continue
        return trends

    except Exception as e:
        print(f"Sector strength check failed ({e}). Skipping sector scoring for this run.")
        return {}
