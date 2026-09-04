"""
discord_alert.py
Formats the day's signals into a readable Discord message and sends it via
webhook. Set the DISCORD_WEBHOOK_URL environment variable before running.
"""
import requests

import config


def format_coverage_line(covered: int, total: int) -> str:
    """
    Data-health canary shown at the top of every post. A total yfinance
    outage would otherwise produce the exact same "nothing to report"
    message as a genuinely quiet day — this makes that distinguishable.
    """
    if total <= 0:
        return "⚠️ Data: 0/0 tickers — universe list came back empty"

    pct = covered / total * 100
    line = f"Data: {covered}/{total} tickers"
    if pct < config.COVERAGE_WARN_PCT:
        return f"⚠️ {line} ({pct:.0f}%) — below {config.COVERAGE_WARN_PCT}% coverage, results may be incomplete"
    return line


def format_message(buy_signals: list, put_signals: list, held_signals: list, market_label: str = None,
                    coverage_line: str = None) -> str:
    lines = ["**📊 Daily Stock Coach**"]
    if coverage_line:
        lines.append(coverage_line)
    if market_label:
        lines.append(market_label)

    sells = [s for s in held_signals if s["signal"] == "SELL"]
    holds = [s for s in held_signals if s["signal"] == "HOLD"]

    if sells:
        lines.append("\n**🔴 SELL — time to get out**")
        for s in sells:
            lines.append(f"`{s['ticker']}` — {s['reason']}. Price now: ${s['current_price']}")
            if s.get("reasoning"):
                lines.append(f"  _{s['reasoning']}_")

    if holds:
        lines.append("\n**🟡 HOLD — keep what you have**")
        for s in holds:
            lines.append(
                f"`{s['ticker']}` — up {s['gain_pct']:+.1f}% since you bought it. "
                f"New safety stop: ${s['suggested_stop']}"
            )
            if s.get("reasoning"):
                lines.append(f"  _{s['reasoning']}_")

    if buy_signals:
        lines.append(f"\n**🟢 BUY — top {len(buy_signals)} to consider**")
        lines.append("_Buy at / Safety stop / Goal price / Score (higher = stronger)_")
        for s in buy_signals:
            lines.append(
                f"`{s['ticker']:<7} Buy ${s['entry']:<8} Stop ${s['stop']:<7} "
                f"Goal ${s['target']:<8} Score {s['score']}`"
            )
            for flag in s.get("flags", []):
                lines.append(f"  ⚠️ {flag}")
            opt = s.get("options")
            if opt:
                vol = opt["volatility"]
                vol_note = f", vol {vol['read']}" if vol.get("available") else ""
                lines.append(
                    f"  🟢 CALL {s['ticker']} ${opt['strike']} exp {opt['expiry']} "
                    f"— ${opt['bid']}/${opt['ask']}, OI {opt['open_interest']}{vol_note}"
                )
            if s.get("reasoning"):
                lines.append(f"  _{s['reasoning']}_")
    else:
        lines.append("\nNothing looked strong enough to buy today.")

    if put_signals:
        lines.append(f"\n**🔴 PUT WATCH — top {len(put_signals)} to consider**")
        lines.append("_Entry / Safety stop / Goal price / Score (higher = stronger)_")
        for s in put_signals:
            lines.append(
                f"`{s['ticker']:<7} Entry ${s['entry']:<8} Stop ${s['stop']:<7} "
                f"Goal ${s['target']:<8} Score {s['score']}`"
            )
            for flag in s.get("flags", []):
                lines.append(f"  ⚠️ {flag}")
            opt = s.get("options")
            if opt:
                vol = opt["volatility"]
                vol_note = f", vol {vol['read']}" if vol.get("available") else ""
                lines.append(
                    f"  🔴 PUT {s['ticker']} ${opt['strike']} exp {opt['expiry']} "
                    f"— ${opt['bid']}/${opt['ask']}, OI {opt['open_interest']}{vol_note}"
                )
            if s.get("reasoning"):
                lines.append(f"  _{s['reasoning']}_")

    return "\n".join(lines)


def send_to_discord(message: str):
    if not config.DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL is not set. Printing message instead:\n")
        print(message)
        return

    # Discord caps messages at 2000 characters — split if needed
    chunks = [message[i:i + 1900] for i in range(0, len(message), 1900)]
    for chunk in chunks:
        resp = requests.post(config.DISCORD_WEBHOOK_URL, json={"content": chunk})
        if resp.status_code not in (200, 204):
            print(f"Discord post failed ({resp.status_code}): {resp.text}")
