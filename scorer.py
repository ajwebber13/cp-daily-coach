"""
scorer.py
Turns the latest indicator values into:
  - a 0-100 confidence score (fully rule-based, no black box)
  - a signal: BUY / SELL / HOLD / PUT WATCH / DO NOTHING
  - entry, stop, and target prices when relevant

This is Drew's TradingView 6-check swing system, automated. Score
breakdown (20 pts each, must sum to 100 — see config.py to change):
  Check 1 - Trend        - price above EMA 200?
  Check 2 - Crossover     - EMA 9 above EMA 20?
  Check 3 - MACD          - MACD line above its signal line?
  Check 4 - RSI            - RSI inside the 40-65 zone?
  Check 5 - Volume          - today's volume above the 30-day average?
  Check 6 - ATR (not scored) - informational only, used to size the stop/target.

Every check is pass/fail, same as reading the chart by hand — no partial
credit for "almost." A 100 means all 5 scored checks passed. This is a
heuristic, not a probability: a 100 doesn't mean "100% chance of being
right," it means every condition in the checklist is currently true.

PUT WATCH mirrors every check: trend below EMA 200 instead of above,
EMA 9 below EMA 20, MACD below signal, same RSI zone, volume still above
average (direction-agnostic).
"""
import numpy as np

import config


# --- Bullish (BUY) checks ---

def check_trend(row) -> bool:
    if np.isnan(row["ema200"]):
        return False
    return row["close"] > row["ema200"]


def check_crossover(row) -> bool:
    return row["ema9"] > row["ema20"]


def check_macd(row) -> bool:
    if np.isnan(row["macd"]) or np.isnan(row["macd_signal"]):
        return False
    return row["macd"] > row["macd_signal"]


def check_rsi(row) -> bool:
    return config.RSI_ZONE_MIN <= row["rsi"] <= config.RSI_ZONE_MAX


def check_volume(row) -> bool:
    if np.isnan(row["rel_vol"]):
        return False
    return row["rel_vol"] > 1.0


def compute_score(row) -> dict:
    c1 = check_trend(row)
    c2 = check_crossover(row)
    c3 = check_macd(row)
    c4 = check_rsi(row)
    c5 = check_volume(row)

    total = (
        (config.WEIGHT_TREND if c1 else 0)
        + (config.WEIGHT_CROSSOVER if c2 else 0)
        + (config.WEIGHT_MACD if c3 else 0)
        + (config.WEIGHT_RSI if c4 else 0)
        + (config.WEIGHT_VOLUME if c5 else 0)
    )

    rsi_flag = ""
    if row["rsi"] >= config.RSI_ZONE_MAX - 2:
        rsi_flag = "near ceiling — approaching overbought"
    elif row["rsi"] <= config.RSI_ZONE_MIN + 5:
        rsi_flag = "near floor"

    return {
        "total": round(total, 1),
        "checks_passed": f"{sum([c1, c2, c3, c4, c5])}/5",
        "trend": c1,
        "crossover": c2,
        "macd": c3,
        "rsi": c4,
        "volume": c5,
        "rsi_value": round(row["rsi"], 2),
        "rsi_flag": rsi_flag,
    }


def trend_aligned(row) -> bool:
    return check_trend(row) and check_crossover(row)


def trend_flipped(row) -> bool:
    return row["ema9"] < row["ema20"]


def entry_stop_target(row) -> dict:
    entry = row["close"]
    stop = entry - config.ATR_STOP_MULT * row["atr"]
    target = entry + config.ATR_TARGET_MULT * row["atr"]
    return {"entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2)}


# --- Bearish (PUT WATCH) checks — mirror of the above ---

def check_trend_bearish(row) -> bool:
    if np.isnan(row["ema200"]):
        return False
    return row["close"] < row["ema200"]


def check_crossover_bearish(row) -> bool:
    return row["ema9"] < row["ema20"]


def check_macd_bearish(row) -> bool:
    if np.isnan(row["macd"]) or np.isnan(row["macd_signal"]):
        return False
    return row["macd"] < row["macd_signal"]


def compute_score_bearish(row) -> dict:
    c1 = check_trend_bearish(row)
    c2 = check_crossover_bearish(row)
    c3 = check_macd_bearish(row)
    c4 = check_rsi(row)          # same zone — direction-agnostic
    c5 = check_volume(row)       # same — direction-agnostic

    total = (
        (config.WEIGHT_TREND if c1 else 0)
        + (config.WEIGHT_CROSSOVER if c2 else 0)
        + (config.WEIGHT_MACD if c3 else 0)
        + (config.WEIGHT_RSI if c4 else 0)
        + (config.WEIGHT_VOLUME if c5 else 0)
    )

    return {
        "total": round(total, 1),
        "checks_passed": f"{sum([c1, c2, c3, c4, c5])}/5",
        "trend": c1,
        "crossover": c2,
        "macd": c3,
        "rsi": c4,
        "volume": c5,
        "rsi_value": round(row["rsi"], 2),
    }


def trend_aligned_bearish(row) -> bool:
    return check_trend_bearish(row) and check_crossover_bearish(row)


def trend_flipped_bearish(row) -> bool:
    """True when a bearish setup should be considered invalidated —
    momentum has turned back up."""
    return row["ema9"] > row["ema20"]


def entry_stop_target_bearish(row) -> dict:
    # Mirror of entry_stop_target: stop sits ABOVE entry (price rising
    # against a put), target sits BELOW entry (price falling in your favor).
    entry = row["close"]
    stop = entry + config.ATR_STOP_MULT * row["atr"]
    target = entry - config.ATR_TARGET_MULT * row["atr"]
    return {"entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2)}


def evaluate_ticker(ticker: str, row, held_position: dict = None, min_score: float = None,
                     min_put_score: float = None) -> dict:
    """
    row: latest indicator row for this ticker (pandas Series)
    held_position: dict from positions.json if currently held, else None
    min_score: overrides config.BUY_SCORE_MIN for this call (used by the
        market regime filter to raise the bar when SPY/QQQ are weak)
    min_put_score: overrides config.PUT_SCORE_MIN for this call
    """
    min_score = config.BUY_SCORE_MIN if min_score is None else min_score
    min_put_score = config.PUT_SCORE_MIN if min_put_score is None else min_put_score
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
                "ticker": ticker, "signal": "SELL", "reason": "EMA 9 crossed back below EMA 20 — trend flipped",
                "score": score["total"], "current_price": round(current_price, 2),
            }

        gain_pct = (current_price / held_position["entry_price"] - 1) * 100
        return {
            "ticker": ticker, "signal": "HOLD",
            "score": score["total"], "current_price": round(current_price, 2),
            "gain_pct": round(gain_pct, 1), "suggested_stop": round(trailing_stop, 2),
        }

    # Not held — evaluate as a potential new entry
    if trend_aligned(row) and score["total"] >= min_score:
        # Compute the ratio from raw (unrounded) prices — rounding entry/
        # stop/target to cents for display can push a mathematically exact
        # ratio just under the threshold by a fraction of a cent.
        raw_entry = row["close"]
        raw_stop = raw_entry - config.ATR_STOP_MULT * row["atr"]
        raw_target = raw_entry + config.ATR_TARGET_MULT * row["atr"]
        raw_risk = raw_entry - raw_stop
        raw_reward = raw_target - raw_entry
        # Round before comparing — floating-point math can turn an exact
        # 1.5 into 1.4999999999999973, which would wrongly fail a strict
        # >= check against a threshold of 1.5.
        reward_risk_ratio = round(raw_reward / raw_risk, 4) if raw_risk > 0 else 0

        if reward_risk_ratio < config.MIN_REWARD_RISK_RATIO:
            return {
                "ticker": ticker, "signal": "DO NOTHING", "score": score["total"],
                "skipped_reason": f"reward:risk only {reward_risk_ratio:.2f}:1 (need {config.MIN_REWARD_RISK_RATIO}:1)",
            }

        levels = entry_stop_target(row)
        return {
            "ticker": ticker, "signal": "BUY", "score": score["total"],
            "score_breakdown": score, "reward_risk_ratio": round(reward_risk_ratio, 2), **levels,
        }

    # BUY didn't clear — check the mirrored bearish setup before giving up
    if trend_aligned_bearish(row):
        score_bearish = compute_score_bearish(row)
        if score_bearish["total"] >= min_put_score:
            raw_entry = row["close"]
            raw_stop = raw_entry + config.ATR_STOP_MULT * row["atr"]
            raw_target = raw_entry - config.ATR_TARGET_MULT * row["atr"]
            raw_risk = raw_stop - raw_entry
            raw_reward = raw_entry - raw_target
            reward_risk_ratio = round(raw_reward / raw_risk, 4) if raw_risk > 0 else 0

            if reward_risk_ratio >= config.MIN_REWARD_RISK_RATIO:
                levels = entry_stop_target_bearish(row)
                return {
                    "ticker": ticker, "signal": "PUT WATCH", "score": score_bearish["total"],
                    "score_breakdown": score_bearish,
                    "reward_risk_ratio": round(reward_risk_ratio, 2), **levels,
                }

    return {"ticker": ticker, "signal": "DO NOTHING", "score": score["total"]}
