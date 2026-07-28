"""
discord_alert.py
Formats the day's signals into a readable Discord message and sends it via
webhook. Set the DISCORD_WEBHOOK_URL environment variable before running.
"""
import requests

import config


def format_message(buy_signals: list, held_signals: list) -> str:
    lines = ["**Daily Stock Coach**"]

    sells = [s for s in held_signals if s["signal"] == "SELL"]
    holds = [s for s in held_signals if s["signal"] == "HOLD"]

    if sells:
        lines.append("\n**SELL**")
        for s in sells:
            lines.append(f"`{s['ticker']}` — {s['reason']} (${s['current_price']})")

    if holds:
        lines.append("\n**HOLD**")
        for s in holds:
            lines.append(
                f"`{s['ticker']}` — {s['gain_pct']:+.1f}% | move stop to ${s['suggested_stop']}"
            )

    if buy_signals:
        lines.append(f"\n**BUY — Top {len(buy_signals)}**")
        lines.append("`Ticker  Entry    Stop    Target   Score`")
        for s in buy_signals:
            lines.append(
                f"`{s['ticker']:<7} ${s['entry']:<8} ${s['stop']:<7} ${s['target']:<8} {s['score']}`"
            )
    else:
        lines.append("\nNo BUY candidates cleared the threshold today.")

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
