"""
grade_signals.py
Grades past BUY/PUT WATCH signals logged by signals_log.py: for each
signal at least GRADE_MIN_DAYS trading days old, checks the price history
since it was posted and records whether target or stop was touched first.

Outcomes:
  hit_target   - target touched before stop
  hit_stop     - stop touched before target (if both are touched on the
                 same daily bar, we can't tell which came first from
                 daily OHLC alone, so this is the conservative call —
                 it never overstates the hit rate)
  expired_flat - neither touched within GRADE_MAX_DAYS trading days
  open         - at least GRADE_MIN_DAYS trading days old, still fewer
                 than GRADE_MAX_DAYS, neither touched yet

Outcomes are written to SIGNALS_OUTCOMES_FILE, keyed by
(date, ticker, signal), rather than mutating signals_log.jsonl in place —
the raw signal log stays a pure, append-only record and this file is
free to be rewritten each grading run.

Run weekly (see .github/workflows/grade-signals.yml). Posts a rollup to
Discord: count resolved, hit rate, and average R achieved, broken out by
BUY vs PUT WATCH.

Usage:
    python grade_signals.py
"""
import json
import os
from datetime import date

import pandas as pd

import config
from discord_alert import send_to_discord

TERMINAL_OUTCOMES = ("hit_target", "hit_stop", "expired_flat")


def _load_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _write_jsonl(path: str, entries: list):
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _key(entry: dict) -> tuple:
    return (entry["date"], entry["ticker"], entry["signal"])


def resolve_outcome(signal: dict, price_df: pd.DataFrame, max_days: int = None) -> tuple:
    """
    Pure, network-free grading logic — takes a signal dict (needs
    'signal' as 'BUY' or 'PUT WATCH', 'entry', 'stop', 'target') and a
    DataFrame of daily bars STRICTLY AFTER the entry date, in
    chronological order, with lowercase 'high'/'low' columns. Row 1 is
    the first trading day after entry.

    Returns (outcome, days_to_resolve). days_to_resolve is None only for
    "open" (not yet resolved and not yet expired).
    """
    max_days = max_days or config.GRADE_MAX_DAYS
    is_bullish = signal["signal"] == "BUY"
    target, stop = signal["target"], signal["stop"]

    rows = price_df.iloc[:max_days]
    for i, (_, row) in enumerate(rows.iterrows(), start=1):
        if is_bullish:
            hit_target = row["high"] >= target
            hit_stop = row["low"] <= stop
        else:
            hit_target = row["low"] <= target
            hit_stop = row["high"] >= stop

        if hit_stop:
            return "hit_stop", i
        if hit_target:
            return "hit_target", i

    if len(rows) >= max_days:
        return "expired_flat", max_days
    return "open", None


def fetch_price_history(ticker: str, since: str):
    """Daily OHLCV from `since` (inclusive) through today. Returns None if
    nothing came back (bad ticker, delisted, network failure)."""
    import yfinance as yf

    df = yf.download(ticker, start=since, auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None

    df = df.rename(columns=str.lower)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    return df if not df.empty else None


def grade_entry(entry: dict) -> dict:
    """
    Returns an outcome record for this signal, or None if it's not yet
    eligible (fewer than GRADE_MIN_DAYS trading days have elapsed) or
    price data couldn't be fetched this run.
    """
    history = fetch_price_history(entry["ticker"], since=entry["date"])
    if history is None:
        return None

    after_entry = history[history.index.strftime("%Y-%m-%d") > entry["date"]]
    if len(after_entry) < config.GRADE_MIN_DAYS:
        return None

    outcome, days = resolve_outcome(entry, after_entry)
    if outcome == "open":
        days = len(after_entry)

    return {
        "date": entry["date"], "ticker": entry["ticker"], "signal": entry["signal"],
        "score": entry.get("score"), "entry": entry.get("entry"), "stop": entry.get("stop"),
        "target": entry.get("target"), "reward_risk": entry.get("reward_risk"),
        "outcome": outcome,
        "days_to_resolve": days if outcome != "open" else None,
        "days_elapsed": len(after_entry),
        "graded_date": str(date.today()),
    }


def grade_signals() -> tuple:
    """
    Grades every signal from SIGNALS_LOG_FILE that isn't already
    terminally resolved. Returns (touched, all_outcomes): the records
    updated this run, and the full current outcomes list.
    """
    signals = _load_jsonl(config.SIGNALS_LOG_FILE)
    outcomes_by_key = {_key(o): o for o in _load_jsonl(config.SIGNALS_OUTCOMES_FILE)}

    touched = []
    for entry in signals:
        key = _key(entry)
        existing = outcomes_by_key.get(key)
        if existing and existing.get("outcome") in TERMINAL_OUTCOMES:
            continue  # already resolved, nothing left to do

        graded = grade_entry(entry)
        if graded is None:
            continue  # too new, or data unavailable this run

        outcomes_by_key[key] = graded
        touched.append(graded)

    all_outcomes = list(outcomes_by_key.values())
    _write_jsonl(config.SIGNALS_OUTCOMES_FILE, all_outcomes)
    return touched, all_outcomes


def summarize(outcomes: list) -> dict:
    """R-multiple convention: hit_target -> +reward_risk (the planned
    ratio, since we only know target was touched, not the exact exit
    price), hit_stop -> -1.0 (the full defined risk unit), expired_flat
    -> 0.0 (no resolution, treated as breakeven for scoring purposes)."""
    resolved = [o for o in outcomes if o["outcome"] in TERMINAL_OUTCOMES]
    if not resolved:
        return None

    hits = sum(1 for o in resolved if o["outcome"] == "hit_target")
    r_values = []
    for o in resolved:
        if o["outcome"] == "hit_target":
            r_values.append(o.get("reward_risk") or 0.0)
        elif o["outcome"] == "hit_stop":
            r_values.append(-1.0)
        else:
            r_values.append(0.0)

    return {
        "count": len(resolved),
        "open_count": len(outcomes) - len(resolved),
        "hit_rate": round(hits / len(resolved) * 100, 1),
        "avg_r": round(sum(r_values) / len(r_values), 2),
    }


def format_rollup_message(all_outcomes: list, newly_graded_count: int) -> str:
    lines = ["**📈 Weekly Signal Grading**"]
    lines.append(f"_Graded {newly_graded_count} signal(s) this run._")

    for signal_type, label in (("BUY", "🟢 BUY"), ("PUT WATCH", "🔴 PUT WATCH")):
        subset = [o for o in all_outcomes if o["signal"] == signal_type]
        summary = summarize(subset)
        if not summary:
            lines.append(f"\n**{label}** — no resolved signals yet.")
            continue
        lines.append(
            f"\n**{label}** — {summary['count']} resolved, {summary['open_count']} still open\n"
            f"Hit rate: {summary['hit_rate']}%  |  Avg R: {summary['avg_r']:+.2f}"
        )

    if not all_outcomes:
        lines.append("\nNo signals logged yet.")

    return "\n".join(lines)


def main():
    touched, all_outcomes = grade_signals()
    message = format_rollup_message(all_outcomes, len(touched))
    send_to_discord(message)
    print(f"Graded {len(touched)} signal(s) this run. {len(all_outcomes)} total tracked.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            send_to_discord(f"⚠️ **Signal grading failed**: {e}")
        except Exception:
            pass
        raise
