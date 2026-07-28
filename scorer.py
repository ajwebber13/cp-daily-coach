"""
scorer.py
Turns the latest indicator values into:
  - a 0-100 confidence score (fully rule-based, no black box)
  - a signal: BUY / SELL / HOLD / DO NOTHING
  - entry, stop, and target prices when relevant

Score breakdown (must sum to 100 — see config.py to change weights):
  Trend alignment   (40 pts) - is price in a confirmed uptrend?
  Volume            (20 pts) - is today's move backed by real volume?
  RSI positioning   (20 pts) - is momentum healthy, not overbought/oversold?
  Volatility        (20 pts) - is the stock calm enough for a clean stop/target?

This is a heuristic, not a probability. A 92 doesn't mean "92% chance of
being right" — it means 92% of the defined conditions for a clean, healthy
trend-following entry are currently true. Treat it as a ranking signal
between tickers, not a statement of certainty.
"""
import numpy as np

import config


def score_trend(row) -> float:
    if row["sma_trend"] is None or np.isnan(row["sma_trend"]):
        return 0.0
    points = 0.0
    if row["close"] > row["sma_trend"]:
        points += config.WEIGHT_TREND / 2
    if row["ema_fast"] > row["ema_slow"]:
        points += config.WEIGHT_TREND / 2
    return points


def score_volume(row) -> float:
    if np.isnan(row["rel_vol"]):
        return 0.0
    # Full points at 2x average volume or higher, scaled linearly below that
    ratio = min(row["rel_vol"] / 2.0, 1.0)
    return max(ratio, 0.0) * config.WEIGHT_VOLUME


def score_rsi(row) -> float:
    # Triangular score peaking at RSI 55, zero at RSI <=30 or >=80
    rsi = row["rsi"]
    distance = abs(rsi - 55)
    scaled = max(0.0, 1 - distance / 25)
    return scaled * config.WEIGHT_RSI


def score_volatility(row) -> float:
    # Lower relative volatility (ATR as % of price) scores higher — caps
    # out at 4% ATR/price, which is already a choppy, hard-to-manage stock.
    atr_pct = row["atr_pct"]
    if np.isnan(atr_pct):
        return 0.0
    scaled = max(0.0, 1 - min(atr_pct / 0.04, 1.0))
    return scaled * config.WEIGHT_VOLATILITY


def compute_score(row) -> dict:
    trend = score_trend(row)
    volume = score_volume(row)
    rsi = score_rsi(row)
    volatility = score_volatility(row)
    total = round(trend + volume + rsi + volatility, 1)
    return {
        "total": total,
        "trend": round(trend, 1),
        "volume": round(volume, 1),
        "rsi": round(rsi, 1),
        "volatility": round(volatility, 1),
    }


def trend_aligned(row) -> bool:
    if row["sma_trend"] is None or np.isnan(row["sma_trend"]):
        return False
    return row["close"] > row["sma_trend"] and row["ema_fast"] > row["ema_slow"]


def trend_flipped(row) -> bool:
    return row["ema_fast"] < row["ema_slow"]


def entry_stop_target(row) -> dict:
    entry = row["close"]
    stop = entry - config.ATR_STOP_MULT * row["atr"]
    target = entry + config.ATR_TARGET_MULT * row["atr"]
    return {"entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2)}


def evaluate_ticker(ticker: str, row, held_position: dict = None) -> dict:
    """
    row: latest indicator row for this ticker (pandas Series)
    held_position: dict from positions.json if currently held, else None
    """
    score = compute_score(row)

    if held_position:
        # Already in this trade — check for an exit trigger
        current_price = row["close"]
        trailing_stop = max(
            held_position.get("stop", 0),
            held_position.get("highest_close", current_price) - config.ATR_STOP_MULT * row["atr"],
        )

        if current_price <= trailing_stop:
            return {
                "ticker": ticker, "signal": "SELL", "reason": "price dropped to your stop-loss level",
                "score": score["total"], "current_price": round(current_price, 2),
            }
        if trend_flipped(row):
            return {
                "ticker": ticker, "signal": "SELL", "reason": "the stock's short-term trend just turned down",
                "score": score["total"], "current_price": round(current_price, 2),
            }

        gain_pct = (current_price / held_position["entry_price"] - 1) * 100
        return {
            "ticker": ticker, "signal": "HOLD",
            "score": score["total"], "current_price": round(current_price, 2),
            "gain_pct": round(gain_pct, 1), "suggested_stop": round(trailing_stop, 2),
        }

    # Not held — evaluate as a potential new entry
    if trend_aligned(row) and score["total"] >= config.BUY_SCORE_MIN:
        levels = entry_stop_target(row)
        return {
            "ticker": ticker, "signal": "BUY", "score": score["total"],
            "score_breakdown": score, **levels,
        }

    return {"ticker": ticker, "signal": "DO NOTHING", "score": score["total"]}
