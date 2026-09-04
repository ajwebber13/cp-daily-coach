"""
discord_alert.py
Formats the day's signals into a readable Discord message and sends it via
webhook. Set the DISCORD_WEBHOOK_URL environment variable before running.
"""
import json

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


def format_signal_card(result: dict) -> str:
    """
    A single, self-contained Discord message ("card") for one BUY or PUT
    WATCH signal: price/entry/stop/target/R:R plus the full indicator
    breakdown from indicators.build_chart_snapshot() (EMA stack, RSI,
    MACD, relative volume, ATR, nearest support/resistance, candlestick
    reads). Sent as its own message, in addition to the compact summary
    table in format_message() — this is the detailed follow-up per pick.

    Always kept under Discord's 2000-char cap on its own, since it's
    posted as a single message (not chunked like format_message's output).
    """
    ticker, signal = result["ticker"], result["signal"]
    is_bullish = signal == "BUY"
    emoji = "🟢" if is_bullish else "🔴"
    verb = "CALL setup" if is_bullish else "PUT setup"

    lines = [f"**{emoji} {ticker} — {verb} (score {result.get('score')})**"]
    lines.append(
        f"Entry ${result.get('entry')} · Stop ${result.get('stop')} · "
        f"Target ${result.get('target')} · R:R {result.get('reward_risk_ratio', '?')}:1"
    )

    for flag in result.get("flags", []):
        lines.append(f"⚠️ {flag}")
    if result.get("levels_caution"):
        lines.append(f"⚠️ {result['levels_caution']}")

    chart = result.get("chart")
    if chart:
        lines.append(
            f"EMA 9/20/50/200: {chart['ema9']} / {chart['ema20']} / {chart['ema50']} / "
            f"{chart['ema200']} — {chart['ema_stack']}"
        )
        lines.append(f"RSI {chart['rsi']} ({chart['rsi_zone']})")
        lines.append(
            f"MACD {chart['macd']} vs signal {chart['macd_signal']} "
            f"(hist {chart['macd_hist']:+}, {chart['macd_direction']})"
        )
        rel_vol_str = f"{chart['rel_vol']}x" if chart.get("rel_vol") is not None else "n/a"
        lines.append(f"Rel volume {rel_vol_str} · ATR {chart['atr']}")

        resistance = ", ".join(f"${p}" for p in chart.get("resistance", [])) or "none nearby"
        support = ", ".join(f"${p}" for p in chart.get("support", [])) or "none nearby"
        lines.append(f"Resistance: {resistance}  |  Support: {support}")
        lines.append(
            f"20d range ${chart['low_20d']}-${chart['high_20d']} · "
            f"52w range ${chart['low_52w']}-${chart['high_52w']}"
        )

        patterns = chart.get("patterns", [])
        lines.append(f"Candles: {', '.join(patterns) if patterns else 'no notable pattern'}")

    opt = result.get("options")
    if opt:
        vol = opt["volatility"]
        vol_note = f", vol {vol['read']}" if vol.get("available") else ""
        label = "CALL" if is_bullish else "PUT"
        lines.append(
            f"{emoji} {label} {ticker} ${opt['strike']} exp {opt['expiry']} "
            f"— ${opt['bid']}/${opt['ask']}, OI {opt['open_interest']}{vol_note}"
        )

    if result.get("reasoning"):
        lines.append(f"_{result['reasoning']}_")

    message = "\n".join(lines)
    if len(message) > 1900:
        message = message[:1897] + "..."
    return message


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


def send_to_discord_with_image(message: str, image_bytes: bytes, filename: str = "chart.png"):
    """
    Same as send_to_discord, but attaches a PNG via the webhook's
    multipart file upload (see chart_image.py). Falls back to a
    text-only post if image_bytes is empty/None — a failed chart render
    should never cost the card itself.
    """
    if not image_bytes:
        send_to_discord(message)
        return

    if not config.DISCORD_WEBHOOK_URL:
        print(f"DISCORD_WEBHOOK_URL is not set. Would attach {filename} "
              f"({len(image_bytes)} bytes). Printing message instead:\n")
        print(message)
        return

    payload = {"content": message[:1900]}
    files = {"file": (filename, image_bytes, "image/png")}
    resp = requests.post(config.DISCORD_WEBHOOK_URL, data={"payload_json": json.dumps(payload)}, files=files)
    if resp.status_code not in (200, 204):
        print(f"Discord image post failed ({resp.status_code}): {resp.text}")
