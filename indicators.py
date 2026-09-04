"""
indicators.py
Computes the inputs for Drew's 6-check swing system: EMA 9, EMA 20,
EMA 200, MACD (line + signal), RSI, ATR, and relative volume. Same math
as the TradingView Overlay/Momentum Toolkit indicators, so a ticker's
score here should match what Drew would read by hand on the chart.

Also computes the extra, informational-only context shown on a signal's
chart card (see discord_alert.format_signal_card): EMA 50, nearby
support/resistance from swing highs/lows, and simple candlestick reads.
None of this feeds the score — it's context for the human reading the
card, same as ATR.
"""
import numpy as np
import pandas as pd

import config

# Candlestick pattern thresholds. Not exposed in config.py — these are
# shape definitions, not tunable strategy parameters.
DOJI_BODY_MAX_PCT = 0.1      # body <= 10% of the bar's range
HAMMER_WICK_RATIO = 2.0      # lower wick >= 2x body
HAMMER_OPPOSITE_WICK_MAX_PCT = 0.3   # upper wick <= 30% of body


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Check 1 & 2 inputs: EMA stack (EMA 50 is informational only, not
    # part of the 6-check score — shown on the chart card as an extra
    # trend read between the 20 and 200)
    df["ema9"] = df["close"].ewm(span=config.EMA_9, adjust=False).mean()
    df["ema20"] = df["close"].ewm(span=config.EMA_20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=config.EMA_50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=config.EMA_200, adjust=False).mean()

    # Check 3 input: MACD (line above/below signal)
    ema_fast_macd = df["close"].ewm(span=config.MACD_FAST, adjust=False).mean()
    ema_slow_macd = df["close"].ewm(span=config.MACD_SLOW, adjust=False).mean()
    df["macd"] = ema_fast_macd - ema_slow_macd
    df["macd_signal"] = df["macd"].ewm(span=config.MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Check 4 input: RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)

    # Check 5 input: relative volume
    df["vol_avg"] = df["volume"].rolling(config.RELVOL_PERIOD).mean()
    df["rel_vol"] = df["volume"] / df["vol_avg"]

    # Check 6 (informational, not scored): ATR, for stop/target sizing
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / config.ATR_PERIOD, adjust=False).mean()

    return df


# --- Support / resistance ---

def find_swing_points(df: pd.DataFrame, order: int = None) -> tuple:
    """
    A swing high is a bar whose high is the max within a window of
    `order` bars on each side; a swing low is the analogous min. Simple
    fractal-style pivot detection — no external TA library.

    Only bars with a full window on both sides can be confirmed, so the
    most recent `order` bars are never returned as swing points.

    Returns (swing_highs, swing_lows), each a list of (index, price).
    """
    order = order or config.SR_SWING_ORDER
    highs, lows = df["high"], df["low"]
    n = len(df)

    swing_highs, swing_lows = [], []
    for i in range(order, n - order):
        window_high = highs.iloc[i - order:i + order + 1]
        if highs.iloc[i] == window_high.max():
            swing_highs.append((df.index[i], float(highs.iloc[i])))

        window_low = lows.iloc[i - order:i + order + 1]
        if lows.iloc[i] == window_low.min():
            swing_lows.append((df.index[i], float(lows.iloc[i])))

    return swing_highs, swing_lows


def find_support_resistance(df: pd.DataFrame, current_price: float = None,
                             lookback_days: int = None, max_levels: int = None,
                             order: int = None) -> dict:
    """
    Nearest support/resistance from swing highs/lows over the last
    `lookback_days` bars, plus the 20-day and 52-week range. df must have
    at least `lookback_days` bars of OHLC history; current_price defaults
    to the last close.
    """
    lookback_days = lookback_days or config.SR_LOOKBACK_DAYS
    max_levels = max_levels or config.SR_MAX_LEVELS
    current_price = df["close"].iloc[-1] if current_price is None else current_price

    recent = df.tail(lookback_days)
    swing_highs, swing_lows = find_swing_points(recent, order=order)

    resistance = sorted({p for _, p in swing_highs if p > current_price})[:max_levels]
    support = sorted({p for _, p in swing_lows if p < current_price}, reverse=True)[:max_levels]

    window_20 = df.tail(20)
    window_52w = df.tail(252)

    return {
        "resistance": [round(p, 2) for p in resistance],
        "support": [round(p, 2) for p in support],
        "low_20d": round(float(window_20["low"].min()), 2),
        "high_20d": round(float(window_20["high"].max()), 2),
        "low_52w": round(float(window_52w["low"].min()), 2),
        "high_52w": round(float(window_52w["high"].max()), 2),
    }


# --- Candlestick patterns ---

def _body(row) -> float:
    return abs(row["close"] - row["open"])


def _range(row) -> float:
    return row["high"] - row["low"]


def _upper_wick(row) -> float:
    return row["high"] - max(row["close"], row["open"])


def _lower_wick(row) -> float:
    return min(row["close"], row["open"]) - row["low"]


def is_doji(row) -> bool:
    rng = _range(row)
    if rng <= 0:
        return False
    return bool(_body(row) <= DOJI_BODY_MAX_PCT * rng)


def is_hammer(row) -> bool:
    body = _body(row)
    if _range(row) <= 0 or body <= 0:
        return False
    return bool(_lower_wick(row) >= HAMMER_WICK_RATIO * body
                and _upper_wick(row) <= HAMMER_OPPOSITE_WICK_MAX_PCT * body)


def is_shooting_star(row) -> bool:
    body = _body(row)
    if _range(row) <= 0 or body <= 0:
        return False
    return bool(_upper_wick(row) >= HAMMER_WICK_RATIO * body
                and _lower_wick(row) <= HAMMER_OPPOSITE_WICK_MAX_PCT * body)


def is_bullish_engulfing(prev_row, row) -> bool:
    prev_bearish = prev_row["close"] < prev_row["open"]
    curr_bullish = row["close"] > row["open"]
    if not (prev_bearish and curr_bullish):
        return False
    return bool(row["open"] <= prev_row["close"] and row["close"] >= prev_row["open"])


def is_bearish_engulfing(prev_row, row) -> bool:
    prev_bullish = prev_row["close"] > prev_row["open"]
    curr_bearish = row["close"] < row["open"]
    if not (prev_bullish and curr_bearish):
        return False
    return bool(row["open"] >= prev_row["close"] and row["close"] <= prev_row["open"])


PATTERN_LABELS = {
    "bullish_engulfing": "Bullish engulfing",
    "bearish_engulfing": "Bearish engulfing",
    "hammer": "Hammer",
    "shooting_star": "Shooting star",
    "doji": "Doji",
    "close_above_prior_high": "Closed above prior bar's high",
}


def detect_candlestick_patterns(df: pd.DataFrame) -> dict:
    """
    Looks at the last 3 bars and grades the shape of the most recent one
    (doji/hammer/shooting_star are single-bar reads) plus the two-bar
    reads that need the prior bar (engulfing, close-above-prior-high).
    Needs at least 1 bar; the two-bar reads are False with fewer than 2.
    """
    recent = df.tail(3)
    if recent.empty:
        return {}

    last = recent.iloc[-1]
    result = {
        "doji": is_doji(last),
        "hammer": is_hammer(last),
        "shooting_star": is_shooting_star(last),
        "bullish_engulfing": False,
        "bearish_engulfing": False,
        "close_above_prior_high": False,
    }

    if len(recent) >= 2:
        prev = recent.iloc[-2]
        result["bullish_engulfing"] = is_bullish_engulfing(prev, last)
        result["bearish_engulfing"] = is_bearish_engulfing(prev, last)
        result["close_above_prior_high"] = bool(last["close"] > prev["high"])

    return result


def describe_candlestick_patterns(patterns: dict) -> list:
    return [label for key, label in PATTERN_LABELS.items() if patterns.get(key)]


# --- Chart card snapshot ---

def ema_stack_label(row) -> str:
    e9, e20, e50, e200 = row["ema9"], row["ema20"], row["ema50"], row["ema200"]
    if e9 > e20 > e50 > e200:
        return "bullish stack (9>20>50>200)"
    if e9 < e20 < e50 < e200:
        return "bearish stack (9<20<50<200)"
    return "mixed"


def rsi_zone_label(rsi: float) -> str:
    if config.RSI_SWEET_MIN <= rsi <= config.RSI_SWEET_MAX:
        return "sweet spot"
    if config.RSI_ZONE_MIN <= rsi <= config.RSI_ZONE_MAX:
        return "in zone"
    return "outside zone"


def macd_direction_label(df: pd.DataFrame) -> str:
    if len(df) < 2:
        return "n/a"
    hist, prev_hist = df["macd_hist"].iloc[-1], df["macd_hist"].iloc[-2]
    if hist > prev_hist:
        return "rising"
    if hist < prev_hist:
        return "falling"
    return "flat"


def build_chart_snapshot(df: pd.DataFrame) -> dict:
    """
    Everything needed to render a signal's chart card: current EMA
    stack, RSI, MACD, volume, ATR, support/resistance, and candlestick
    reads. df must already have add_indicators() applied and enough
    history (60+ bars for support/resistance, ideally 252+ for the
    52-week range).
    """
    row = df.iloc[-1]
    sr = find_support_resistance(df, row["close"])
    patterns = detect_candlestick_patterns(df)
    rel_vol = row["rel_vol"]

    return {
        "price": round(float(row["close"]), 2),
        "ema9": round(float(row["ema9"]), 2),
        "ema20": round(float(row["ema20"]), 2),
        "ema50": round(float(row["ema50"]), 2),
        "ema200": round(float(row["ema200"]), 2),
        "ema_stack": ema_stack_label(row),
        "rsi": round(float(row["rsi"]), 2),
        "rsi_zone": rsi_zone_label(row["rsi"]),
        "macd": round(float(row["macd"]), 4),
        "macd_signal": round(float(row["macd_signal"]), 4),
        "macd_hist": round(float(row["macd_hist"]), 4),
        "macd_direction": macd_direction_label(df),
        "rel_vol": None if np.isnan(rel_vol) else round(float(rel_vol), 2),
        "atr": round(float(row["atr"]), 2),
        "support": sr["support"],
        "resistance": sr["resistance"],
        "low_20d": sr["low_20d"], "high_20d": sr["high_20d"],
        "low_52w": sr["low_52w"], "high_52w": sr["high_52w"],
        "patterns": describe_candlestick_patterns(patterns),
    }


def levels_caution(signal: str, entry: float, target: float, atr: float,
                    resistance: list, support: list, low_52w: float, high_52w: float) -> str:
    """
    Flags — never scores — a BUY/PUT WATCH whose target runs past a
    level that's likely to matter before it gets there: a wall right at
    entry (nearest resistance/support within 1 ATR), or a target set
    beyond the nearest resistance/support or the 52-week high/low. Purely
    informational, shown on the chart card; does not change the score or
    block the signal.

    Returns a "Levels: ..." string listing every reason that applies
    (joined with "; "), or None if nothing triggered.
    """
    reasons = []

    if signal == "BUY":
        nearest = resistance[0] if resistance else None
        if nearest is not None and atr > 0 and nearest > entry and (nearest - entry) <= atr:
            reasons.append(f"resistance ${nearest} within {(nearest - entry) / atr:.2f} ATR of entry")
        if nearest is not None and target > nearest:
            reasons.append(f"target above nearest resistance (${nearest})")
        if target > high_52w:
            reasons.append("target above 52w high")

    else:  # PUT WATCH
        nearest = support[0] if support else None
        if nearest is not None and atr > 0 and nearest < entry and (entry - nearest) <= atr:
            reasons.append(f"support ${nearest} within {(entry - nearest) / atr:.2f} ATR of entry")
        if nearest is not None and target < nearest:
            reasons.append(f"target below nearest support (${nearest})")
        if target < low_52w:
            reasons.append("target below 52w low")

    if not reasons:
        return None
    return "Levels: " + "; ".join(reasons)
