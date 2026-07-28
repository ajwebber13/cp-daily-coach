"""
midday.py
Run around midday. Same lightweight "what's moving" check as
premarket.py — no scoring, no BUY/SELL/HOLD, just flags S&P 500 tickers
that have moved 3%+ so far today. Reuses premarket.py's logic since it's
the same kind of check, just at a different point in the trading day.

Usage:
    python midday.py
"""
import config
import universe
from discord_alert import send_to_discord
from premarket import get_previous_closes, get_premarket_prices, find_movers


def format_midday_message(movers) -> str:
    lines = ["**🕛 Midday Check-In**"]

    if movers.empty:
        lines.append(f"\nNothing has moved more than {config.PREMARKET_MOVE_THRESHOLD}% so far today.")
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


def run_midday_scan():
    print("Loading S&P 500 universe...")
    tickers = universe.get_sp500_tickers()

    print(f"Checking today's movement so far for {len(tickers)} tickers...")
    movers = find_movers(tickers)

    message = format_midday_message(movers)
    send_to_discord(message)

    print(f"\nDone. {len(movers)} tickers moved {config.PREMARKET_MOVE_THRESHOLD}%+ so far today.")


if __name__ == "__main__":
    run_midday_scan()
