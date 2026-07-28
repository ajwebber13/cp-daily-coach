"""
scan.py
Run this once a day (manually, or on a schedule — see README for the
Windows Task Scheduler / cron setup). It:
  1. Loads the S&P 500 universe (cached weekly)
  2. Downloads recent price history in batches
  3. Scores every ticker and checks your open positions
  4. Sends BUY / SELL / HOLD signals to Discord

Usage:
    python scan.py
"""
import sys

import pandas as pd

import config
import universe
import positions
from indicators import add_indicators
from scorer import evaluate_ticker
from discord_alert import format_message, send_to_discord


def batch_download(tickers: list) -> dict:
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("yfinance is not installed. Run: pip install yfinance") from e

    price_data = {}
    for i in range(0, len(tickers), config.BATCH_SIZE):
        batch = tickers[i:i + config.BATCH_SIZE]
        print(f"Downloading batch {i // config.BATCH_SIZE + 1} ({len(batch)} tickers)...")
        raw = yf.download(
            batch,
            period=f"{config.LOOKBACK_DAYS}d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )

        for ticker in batch:
            try:
                if len(batch) == 1:
                    df = raw
                else:
                    df = raw[ticker]
                df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
                if len(df) > config.SMA_TREND:
                    price_data[ticker] = df
            except (KeyError, Exception):
                continue  # skip tickers with no/bad data rather than crash the whole scan

    return price_data


def run_scan():
    print("Loading S&P 500 universe...")
    tickers = universe.get_sp500_tickers()

    print(f"Downloading data for {len(tickers)} tickers...")
    price_data = batch_download(tickers)
    print(f"Got usable data for {len(price_data)} of {len(tickers)} tickers.")

    held = positions.list_positions()

    buy_candidates = []
    held_results = []

    for ticker, df in price_data.items():
        df = add_indicators(df)
        latest_row = df.iloc[-1]

        if ticker in held:
            positions.update_highest_close(ticker, latest_row["close"])
            held = positions.list_positions()  # reload after update
            result = evaluate_ticker(ticker, latest_row, held_position=held[ticker])
            held_results.append(result)
            if result["signal"] == "SELL":
                positions.remove_position(ticker)
        else:
            result = evaluate_ticker(ticker, latest_row, held_position=None)
            if result["signal"] == "BUY":
                buy_candidates.append(result)

    buy_candidates.sort(key=lambda x: x["score"], reverse=True)
    top_buys = buy_candidates[:config.TOP_N_RESULTS]

    message = format_message(top_buys, held_results)
    send_to_discord(message)

    print(f"\nDone. {len(top_buys)} BUY candidates, {len(held_results)} held positions checked.")


if __name__ == "__main__":
    run_scan()
