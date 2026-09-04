"""
premarket.py
Run before the market opens. Re-evaluates every S&P 500 ticker against
your 6-check swing checklist using the current pre-market price as a
stand-in for today's close — so you see who's already clearing the
checklist before the bell, not just who's moving.

Volume isn't scored here: pre-market volume is a small, uneven fraction
of a full session and there's no reliable 30-day pre-market average to
compare it against, so a volume "pass" pre-market would be misleading.
This runs a 4-check score instead (Trend, Crossover, MACD, RSI), scaled
to 100 — Volume gets checked for real once scan.py runs after close.

This is an early read using an ESTIMATED price, not a BUY signal. The
pre-market price can (and often does) move before the open. Confirm
against scan.py's after-close numbers before acting on anything here.

Usage:
    python premarket.py
"""
import pandas as pd

import config
import universe
from indicators import add_indicators
from scorer import check_trend, check_crossover, check_macd, check_rsi, entry_stop_target
from discord_alert import send_to_discord, format_coverage_line
from scan import batch_download


def get_premarket_prices(tickers: list) -> dict:
    """Latest pre-market tick for each ticker (most recent 1-min bar before/at now)."""
    import yfinance as yf

    prices = {}
    for i in range(0, len(tickers), config.BATCH_SIZE):
        batch = tickers[i:i + config.BATCH_SIZE]
        print(f"Fetching pre-market prices, batch {i // config.BATCH_SIZE + 1}...")
        raw = yf.download(batch, period="1d", interval="1m", prepost=True,
                           group_by="ticker", threads=True, progress=False)
        for ticker in batch:
            try:
                df = raw if len(batch) == 1 else raw[ticker]
                df = df.dropna()
                if not df.empty:
                    prices[ticker] = df["Close"].iloc[-1]
            except Exception:
                continue
    return prices


def estimate_today_row(daily_df: pd.DataFrame, premarket_price: float) -> pd.Series:
    """
    Appends a synthetic 'today' bar using the pre-market price and re-runs
    the same indicator math scan.py uses — approximates where EMA9/20/200,
    MACD, and RSI would sit if the pre-market price held into the open.
    Volume on the synthetic bar is a placeholder (carried from the prior
    day) since it isn't scored here — don't read it as real volume.
    """
    last_date = daily_df.index[-1]
    synthetic_date = last_date + pd.Timedelta(days=1)
    synthetic_row = pd.DataFrame({
        "open": [premarket_price], "high": [premarket_price],
        "low": [premarket_price], "close": [premarket_price],
        "volume": [daily_df["volume"].iloc[-1]],
    }, index=[synthetic_date])
    extended = pd.concat([daily_df, synthetic_row])
    extended = add_indicators(extended)
    return extended.iloc[-1]


def compute_premarket_score(row) -> dict:
    c1 = check_trend(row)
    c2 = check_crossover(row)
    c3 = check_macd(row)
    c4 = check_rsi(row)
    total = round(sum([c1, c2, c3, c4]) / 4 * 100, 1)
    return {
        "total": total,
        "checks_passed": f"{sum([c1, c2, c3, c4])}/4",
        "trend": c1, "crossover": c2, "macd": c3, "rsi": c4,
    }


def run_premarket_scan():
    print("Loading S&P 500 universe...")
    tickers = universe.get_sp500_tickers()

    print(f"Downloading daily history for {len(tickers)} tickers...")
    price_data = batch_download(tickers)
    print(f"Got usable data for {len(price_data)} of {len(tickers)} tickers.")
    coverage_line = format_coverage_line(len(price_data), len(tickers))

    print(f"Fetching pre-market prices for {len(price_data)} tickers...")
    premarket_prices = get_premarket_prices(list(price_data.keys()))

    watch_list = []
    for ticker, daily_df in price_data.items():
        if ticker not in premarket_prices:
            continue
        pm_price = premarket_prices[ticker]
        try:
            row = estimate_today_row(daily_df, pm_price)
        except Exception:
            continue

        score = compute_premarket_score(row)
        # Require trend + crossover (same gate as scan.py's BUY logic) plus
        # at least 3 of 4 checks passing.
        if score["trend"] and score["crossover"] and score["total"] >= 75:
            levels = entry_stop_target(row)
            watch_list.append({
                "ticker": ticker,
                "premarket_price": round(pm_price, 2),
                "score": score["total"],
                "checks_passed": score["checks_passed"],
                **levels,
            })

    watch_list.sort(key=lambda x: x["score"], reverse=True)

    message = format_premarket_message(watch_list, coverage_line=coverage_line)
    send_to_discord(message)

    print(f"\nDone. {len(watch_list)} ticker(s) clearing the checklist pre-market.")


def format_premarket_message(watch_list: list, coverage_line: str = None) -> str:
    lines = ["**🌅 Before the Market Opens — 6-Check Watch List**"]
    if coverage_line:
        lines.append(coverage_line)
    lines.append(
        "_Estimated from the current pre-market price. Volume isn't scored "
        "here (too thin before the open) — this is Trend/Crossover/MACD/RSI "
        "only. Confirm at the open before acting._"
    )

    if not watch_list:
        lines.append("\nNothing is clearing the checklist pre-market right now.")
        return "\n".join(lines)

    lines.append(f"\n**Clearing 3-4 of 4 checks ({len(watch_list)} tickers)**")
    lines.append("_Ticker / Pre-market price / Est. stop / Est. target / Checks (Score)_")
    for w in watch_list[:config.TOP_N_RESULTS]:
        lines.append(
            f"`{w['ticker']:<7} ${w['premarket_price']:<8} Stop ${w['stop']:<7} "
            f"Target ${w['target']:<8} {w['checks_passed']} ({w['score']})`"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    try:
        run_premarket_scan()
    except Exception as e:
        try:
            send_to_discord(f"⚠️ **Pre-market scan failed**: {e}")
        except Exception:
            pass
        raise
