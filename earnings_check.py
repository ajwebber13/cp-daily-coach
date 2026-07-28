"""
earnings_check.py
"Your model doesn't need to read every article — just know if a major
event is imminent." Checks whether a ticker has earnings coming up soon.
An earnings surprise can gap a stock past its stop-loss overnight, which
defeats the whole point of the ATR-based risk management this coach uses.

Only called on tickers that already passed every other filter (a small
list, not all 500) — yfinance doesn't support checking earnings dates in
batch, so checking the full universe would be slow and likely to get
rate-limited.
"""
from datetime import datetime

import config


def days_until_next_earnings(ticker: str) -> int | None:
    """
    Returns days until the next earnings date, or None if unknown
    (no data, ticker doesn't report earnings, or the lookup failed —
    treated as "no imminent earnings known" rather than blocking the buy
    on a data gap).
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        earnings_dates = t.get_earnings_dates(limit=4)
        if earnings_dates is None or earnings_dates.empty:
            return None

        today = datetime.now(earnings_dates.index.tz)
        future_dates = earnings_dates.index[earnings_dates.index >= today]
        if len(future_dates) == 0:
            return None

        next_date = future_dates.min()
        return (next_date - today).days

    except Exception as e:
        print(f"Earnings check skipped for {ticker}: {e}")
        return None


def filter_imminent_earnings(candidates: list) -> list:
    """
    Takes a list of BUY candidate dicts (must have 'ticker' key), checks
    each for imminent earnings, and returns only the ones clear of that
    window. Candidates that get excluded are not silently dropped from
    view — see scan.py, which reports how many were skipped and why.
    """
    clear = []
    for c in candidates:
        days_away = days_until_next_earnings(c["ticker"])
        if days_away is not None and 0 <= days_away <= config.EARNINGS_AVOID_DAYS:
            c["skipped_reason"] = f"earnings in {days_away} day(s) — too risky to enter now"
            continue
        clear.append(c)
    return clear
