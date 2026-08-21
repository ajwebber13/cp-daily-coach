"""
scan.py
Run this once a day (manually, or on a schedule — see README for the
Windows Task Scheduler / cron setup). It:
  1. Loads the S&P 500 universe (cached weekly)
  2. Downloads recent price history in batches
  3. Scores every ticker and checks your open positions
  4. Sends BUY / PUT WATCH / SELL / HOLD signals to Discord

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
from ai_reasoning import add_reasoning_to_results
from options_overlay import add_options_to_results
from market_regime import get_market_regime
from earnings_check import filter_imminent_earnings


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
                if len(df) > config.EMA_200:
                    price_data[ticker] = df
            except (KeyError, Exception):
                continue  # skip tickers with no/bad data rather than crash the whole scan

    return price_data


def run_scan():
    print("Checking overall market trend (SPY/QQQ)...")
    regime = get_market_regime()
    print(f"Market regime: {regime['label']}")
    min_score = config.BUY_SCORE_MIN + regime["score_adjustment"]
    min_put_score = config.PUT_SCORE_MIN  # flat threshold — Drew reads market context from charts himself

    print("Loading S&P 500 universe...")
    tickers = universe.get_sp500_tickers()

    print(f"Downloading data for {len(tickers)} tickers...")
    price_data = batch_download(tickers)
    print(f"Got usable data for {len(price_data)} of {len(tickers)} tickers.")

    held = positions.list_positions()

    buy_candidates = []
    put_candidates = []
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
            result = evaluate_ticker(ticker, latest_row, held_position=None, min_score=min_score,
                                      min_put_score=min_put_score)
            if result["signal"] == "BUY":
                buy_candidates.append(result)
            elif result["signal"] == "PUT WATCH":
                put_candidates.append(result)

    buy_candidates.sort(key=lambda x: x["score"], reverse=True)
    put_candidates.sort(key=lambda x: x["score"], reverse=True)

    check_pool = buy_candidates[:config.EARNINGS_CHECK_POOL]
    put_check_pool = put_candidates[:config.EARNINGS_CHECK_POOL]

    print(f"Checking earnings dates for top {len(check_pool) + len(put_check_pool)} candidates...")
    clear_of_earnings = filter_imminent_earnings(check_pool)
    clear_puts_of_earnings = filter_imminent_earnings(put_check_pool)
    excluded_count = (len(check_pool) - len(clear_of_earnings)) + \
                      (len(put_check_pool) - len(clear_puts_of_earnings))
    if excluded_count:
        print(f"Excluded {excluded_count} candidate(s) with earnings coming up soon.")

    top_buys = clear_of_earnings[:config.TOP_N_RESULTS]
    top_puts = clear_puts_of_earnings[:config.TOP_N_PUT_RESULTS]

    if config.OPTIONS_OVERLAY_ENABLED:
        print("Checking options liquidity for top picks...")
        add_options_to_results(top_buys)
        add_options_to_results(top_puts)

    if config.AI_REASONING_ENABLED:
        print("Generating AI reasoning for top picks...")
        add_reasoning_to_results(top_buys)
        add_reasoning_to_results(top_puts)
        add_reasoning_to_results(held_results)

    message = format_message(top_buys, top_puts, held_results, market_label=regime["label"])
    send_to_discord(message)

    print(f"\nDone. {len(top_buys)} BUY candidates, {len(top_puts)} PUT WATCH candidates, "
          f"{len(held_results)} held positions checked.")


if __name__ == "__main__":
    run_scan()
