"""
universe.py
Gets the S&P 500 ticker list. Default source is a static CSV bundled with
this tool (sp500_static.csv) — no network call needed, so this can't break
on a firewall/proxy that blocks GitHub or Wikipedia.

The list goes stale slowly (a handful of changes per year), so an optional
online refresh is available: run `python universe.py --refresh` every few
months to try updating it. If the refresh fails for any reason, it just
falls back to the static file — no crash, no giant error dumps.
"""
import os
import sys

import pandas as pd
import requests

import config

STATIC_FILE = "sp500_static.csv"
GITHUB_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"


def _short_error(e: Exception, limit: int = 150) -> str:
    """Never print a raw exception directly — some libraries embed full
    response bodies in their error text, which floods the terminal."""
    text = str(e).replace("\n", " ")
    return text[:limit] + ("..." if len(text) > limit else "")


def get_sp500_tickers(refresh: bool = False) -> list:
    if refresh:
        try:
            resp = requests.get(GITHUB_CSV_URL, timeout=15)
            resp.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(resp.text))
            tickers = [t.replace(".", "-") for t in df["Symbol"].tolist()]
            pd.DataFrame({"ticker": tickers}).to_csv(STATIC_FILE, index=False)
            print(f"Refreshed: {len(tickers)} tickers saved to {STATIC_FILE}.")
            return tickers
        except Exception as e:
            print(f"Refresh failed ({_short_error(e)}). Using existing static list.")

    if not os.path.exists(STATIC_FILE):
        raise FileNotFoundError(
            f"{STATIC_FILE} is missing. Either run 'python universe.py --refresh' "
            f"with a working internet connection, or copy the file back in."
        )

    df = pd.read_csv(STATIC_FILE)
    return df["ticker"].tolist()


if __name__ == "__main__":
    do_refresh = "--refresh" in sys.argv
    tickers = get_sp500_tickers(refresh=do_refresh)
    print(f"{len(tickers)} tickers loaded: {tickers[:10]}...")
