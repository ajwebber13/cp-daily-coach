"""
premarket.py
Run before the market opens. Flags S&P 500 tickers moving significantly
up or down in pre-market trading, so you know what's in motion before the
bell — separate from the after-close BUY/SELL/HOLD scan in scan.py.

This is awareness, not a signal: a stock moving pre-market isn't
automatically a buy or a sell. It just tells you where the action is.

Usage:
    python premarket.py
"""
import sys

import pandas as pd

import config
import universe
from discord_alert import send_to_discord


def get_previous_closes(tickers: list) -> dict:
    """Most recent completed regular-session close for each ticker."""
    import yfinance as yf

    closes = {}
    for i in range(0, len(tickers), config.BATCH_SIZE):
        batch = tickers[i:i + config.BATCH_SIZE]
        print(f"Fetching previous closes, batch {i // config.BATCH_SIZE + 1}...")
        raw = yf.download(batch, period="5d", interval="1d", auto_adjust=True,
                           group_by="ticker", threads=True, progress=False)
        for ticker in batch:
            try:
                df = raw if len(batch) == 1 else raw[ticker]
                df = df.dropna()
                if not df.empty:
                    closes[ticker] = df["Close"].iloc[-1]
            except Exception:
                continue
    return closes


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


def find_movers(tickers: list) -> pd.DataFrame:
    prev_close = get_previous_closes(tickers)
    premarket = get_premarket_prices(tickers)

    rows = []
    for ticker in tickers:
        if ticker not in prev_close or ticker not in premarket:
            continue
        pc, pm = prev_close[ticker], premarket[ticker]
        if pc <= 0:
            continue
        pct_change = (pm - pc) / pc * 100
        if abs(pct_change) >= config.PREMARKET_MOVE_THRESHOLD:
            rows.append({
                "ticker": ticker,
                "prev_close": round(pc, 2),
                "premarket_price": round(pm, 2),
                "pct_change": round(pct_change, 2),
            })

    return pd.DataFrame(rows)


def format_premarket_message(movers: pd.DataFrame) -> str:
    lines = ["**🌅 Before the Market Opens**"]

    if movers.empty:
        lines.append(f"\nNothing is moving much yet — no stock changed more than {config.PREMARKET_MOVE_THRESHOLD}%.")
        return "\n".join(lines)

    gainers = movers[movers["pct_change"] > 0].sort_values("pct_change", ascending=False).head(config.PREMARKET_TOP_N)
    losers = movers[movers["pct_change"] < 0].sort_values("pct_change").head(config.PREMARKET_TOP_N)

    if not gainers.empty:
        lines.append("\n**⬆️ Going Up**")
        lines.append("_Yesterday's price / Price now / Change_")
        for _, r in gainers.iterrows():
            lines.append(f"`{r['ticker']:<7} ${r['prev_close']:<10} ${r['premarket_price']:<8} +{r['pct_change']}%`")

    if not losers.empty:
        lines.append("\n**⬇️ Going Down**")
        lines.append("_Yesterday's price / Price now / Change_")
        for _, r in losers.iterrows():
            lines.append(f"`{r['ticker']:<7} ${r['prev_close']:<10} ${r['premarket_price']:<8} {r['pct_change']}%`")

    return "\n".join(lines)


def run_premarket_scan():
    print("Loading S&P 500 universe...")
    tickers = universe.get_sp500_tickers()

    print(f"Checking pre-market movement for {len(tickers)} tickers...")
    movers = find_movers(tickers)

    message = format_premarket_message(movers)
    send_to_discord(message)

    print(f"\nDone. {len(movers)} tickers moved {config.PREMARKET_MOVE_THRESHOLD}%+ pre-market.")


if __name__ == "__main__":
    run_premarket_scan()
