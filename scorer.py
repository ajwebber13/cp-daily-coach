"""
scorer.py
Turns the latest indicator values into:
  - a 0-100 confidence score (fully rule-based, no black box)
  - a signal: BUY / SELL / HOLD / PUT WATCH / DO NOTHING
  - entry, stop, and target prices when relevant
  - caution flags for any check that only marginally passed

This is Drew's TradingView 6-check swing system, automated. Score
breakdown (20 pts max each, must sum to 100 — see config.py to change):
  Check 1 - Trend        - price above EMA 200?
  Check 2 - Crossover     - EMA 9 above EMA 20?
  Check 3 - MACD          - MACD line above its signal line?
  Check 4 - RSI            - RSI inside the 40-65 zone?
  Check 5 - Volume          - today's volume above the 30-day average?
  Check 6 - ATR (not scored) - informational only, used to size the stop/target.

Each check grades on THREE tiers, not just pass/fail — same distinction
Drew makes reading the chart by hand ("RSI near ceiling", "crossover too
tight", "volume looks like a spike"):
  - FULL  (20 pts) - clean pass, comfortably inside the healthy range
  - HALF  (10 pts) - marginal pass - technically clears the bar, but
                       thin/edge-case - a caution flag is attached
  - FAIL  (0 pts)  - doesn't clear the bar at all

A 100 means every check passed clean, no cautions. A ticker can pass all
5 checks and still fall short of 100 if any of them were marginal. This
is a heuristic, not a probability — a 100 doesn't mean "100% chance of
being right," it means every condition is currently true and clean.

PUT WATCH mirrors every check: trend below EMA 200 instead of above,
EMA 9 below EMA 20, MACD below signal, same RSI zone, volume still above
average (direction-agnostic).
"""
import numpy as np

import config


FULL, HALF, FAIL = 20, 10, 0


# --- Bullish (BUY) checks — each returns (points, flag_text_or_None) ---

def grade_trend(row) -> tuple:
    if np.isnan(row["ema200"]) or row["close"] <= row["ema200"]:
        return FAIL, None
    margin = (row["close"] / row["ema200"]) - 1
    if margin >= config.TREND_MARGIN_PCT:
        return FULL, None
    return HALF, f"just reclaimed EMA 200 ({margin*100:.2f}% above) — thin margin"


def grade_crossover(row) -> tuple:
    if row["ema9"] <= row["ema20"]:
        return FAIL, None
    margin = (row["ema9"] / row["ema20"]) - 1
    if margin >= config.CROSSOVER_MARGIN_PCT:
        return FULL, None
    gap = row["ema9"] - row["ema20"]
    return HALF, f"EMA 9/20 crossover is tight (${gap:.2f} apart) — weak separation"


def grade_macd(row) -> tuple:
    if np.isnan(row["macd"]) or np.isnan(row["macd_signal"]) or row["macd"] <= row["macd_signal"]:
        return FAIL, None
    gap_pct = (row["macd"] - row["macd_signal"]) / row["close"]
    if gap_pct >= config.MACD_MARGIN_PCT:
        return FULL, None
    return HALF, "MACD just barely above signal — momentum hasn't confirmed strongly yet"


def grade_rsi(row) -> tuple:
    rsi = row["rsi"]
    if rsi < config.RSI_ZONE_MIN or rsi > config.RSI_ZONE_MAX:
        return FAIL, None
    if config.RSI_SWEET_MIN <= rsi <= config.RSI_SWEET_MAX:
        return FULL, None
    if rsi > config.RSI_SWEET_MAX:
        return HALF, f"RSI {rsi:.1f} — near ceiling, approaching overbought"
    return HALF, f"RSI {rsi:.1f} — near floor"


def grade_volume(row) -> tuple:
    rel_vol = row["rel_vol"]
    if np.isnan(rel_vol) or rel_vol < 1.0:
        return FAIL, None
    if rel_vol <= config.VOLUME_IDEAL_MAX:
        return FULL, None
    return HALF, f"volume {rel_vol:.1f}x average — unusually high, could be a news-driven spike"


def check_trend(row) -> bool:
    return grade_trend(row)[0] > FAIL


def check_crossover(row) -> bool:
    return grade_crossover(row)[0] > FAIL


def check_macd(row) -> bool:
    return grade_macd(row)[0] > FAIL


def check_rsi(row) -> bool:
    return grade_rsi(row)[0] > FAIL


def check_volume(row) -> bool:
    return grade_volume(row)[0] > FAIL


def compute_score(row) -> dict:
    pts_trend, flag_trend = grade_trend(row)
    pts_crossover, flag_crossover = grade_crossover(row)
    pts_macd, flag_macd = grade_macd(row)
    pts_rsi, flag_rsi = grade_rsi(row)
    pts_volume, flag_volume = grade_volume(row)

    total = pts_trend + pts_crossover + pts_macd + pts_rsi + pts_volume
    passed = sum([pts_trend > FAIL, pts_crossover > FAIL, pts_macd > FAIL,
                  pts_rsi > FAIL, pts_volume > FAIL])
    flags = [f for f in [flag_trend, flag_crossover, flag_macd, flag_rsi, flag_volume] if f]

    return {
        "total": total,
        "checks_passed": f"{passed}/5",
        "trend": pts_trend > FAIL,
        "crossover": pts_crossover > FAIL,
        "macd": pts_macd > FAIL,
        "rsi": pts_rsi > FAIL,
        "volume": pts_volume > FAIL,
        "rsi_value": round(row["rsi"], 2),
        "flags": flags,
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

def grade_trend_bearish(row) -> tuple:
    if np.isnan(row["ema200"]) or row["close"] >= row["ema200"]:
        return FAIL, None
    margin = 1 - (row["close"] / row["ema200"])
    if margin >= config.TREND_MARGIN_PCT:
        return FULL, None
    return HALF, f"just broke below EMA 200 ({margin*100:.2f}% under) — thin margin"


def grade_crossover_bearish(row) -> tuple:
    if row["ema9"] >= row["ema20"]:
        return FAIL, None
    margin = 1 - (row["ema9"] / row["ema20"])
    if margin >= config.CROSSOVER_MARGIN_PCT:
        return FULL, None
    gap = row["ema20"] - row["ema9"]
    return HALF, f"EMA 9/20 crossover is tight (${gap:.2f} apart) — weak separation"


def grade_macd_bearish(row) -> tuple:
    if np.isnan(row["macd"]) or np.isnan(row["macd_signal"]) or row["macd"] >= row["macd_signal"]:
        return FAIL, None
    gap_pct = (row["macd_signal"] - row["macd"]) / row["close"]
    if gap_pct >= config.MACD_MARGIN_PCT:
        return FULL, None
    return HALF, "MACD just barely below signal — momentum hasn't confirmed strongly yet"


def check_trend_bearish(row) -> bool:
    return grade_trend_bearish(row)[0] > FAIL


def check_crossover_bearish(row) -> bool:
    return grade_crossover_bearish(row)[0] > FAIL


def check_macd_bearish(row) -> bool:
    return grade_macd_bearish(row)[0] > FAIL


def compute_score_bearish(row) -> dict:
    pts_trend, flag_trend = grade_trend_bearish(row)
    pts_crossover, flag_crossover = grade_crossover_bearish(row)
    pts_macd, flag_macd = grade_macd_bearish(row)
    pts_rsi, flag_rsi = grade_rsi(row)      # same zone — direction-agnostic
    pts_volume, flag_volume = grade_volume(row)  # same — direction-agnostic

    total = pts_trend + pts_crossover + pts_macd + pts_rsi + pts_volume
    passed = sum([pts_trend > FAIL, pts_crossover > FAIL, pts_macd > FAIL,
                  pts_rsi > FAIL, pts_volume > FAIL])
    flags = [f for f in [flag_trend, flag_crossover, flag_macd, flag_rsi, flag_volume] if f]

    return {
        "total": total,
        "checks_passed": f"{passed}/5",
        "trend": pts_trend > FAIL,
        "crossover": pts_crossover > FAIL,
        "macd": pts_macd > FAIL,
        "rsi": pts_rsi > FAIL,
        "volume": pts_volume > FAIL,
        "rsi_value": round(row["rsi"], 2),
        "flags": flags,
    }


def trend_aligned_bearish(row) -> bool:
    return check_trend_bearish(row) and check_crossover_bearish(row)


def trend_flipped_bearish(row) -> bool:
    """True when a bearish setup should be considered invalidated —
    momentum has turned back up."""
    return row["ema9"] > row["ema20"]


def entry_stop_target_bearish(row) -> dict:
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

    if trend_aligned(row) and score["total"] >= min_score:
        raw_entry = row["close"]
        raw_stop = raw_entry - config.ATR_STOP_MULT * row["atr"]
        raw_target = raw_entry + config.ATR_TARGET_MULT * row["atr"]
        raw_risk = raw_entry - raw_stop
        raw_reward = raw_target - raw_entry
        reward_risk_ratio = round(raw_reward / raw_risk, 4) if raw_risk > 0 else 0

        if reward_risk_ratio < config.MIN_REWARD_RISK_RATIO:
            return {
                "ticker": ticker, "signal": "DO NOTHING", "score": score["total"],
                "skipped_reason": f"reward:risk only {reward_risk_ratio:.2f}:1 (need {config.MIN_REWARD_RISK_RATIO}:1)",
            }

        levels = entry_stop_target(row)
        return {
            "ticker": ticker, "signal": "BUY", "score": score["total"],
            "score_breakdown": score, "flags": score["flags"],
            "reward_risk_ratio": round(reward_risk_ratio, 2), **levels,
        }

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
                    "score_breakdown": score_bearish, "flags": score_bearish["flags"],
                    "reward_risk_ratio": round(reward_risk_ratio, 2), **levels,
                }

    return {"ticker": ticker, "signal": "DO NOTHING", "score": score["total"]}
