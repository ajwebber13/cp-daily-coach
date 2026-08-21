"""
indicators.py
Computes the inputs for Drew's 6-check swing system: EMA 9, EMA 20,
EMA 200, MACD (line + signal), RSI, ATR, and relative volume. Same math
as the TradingView Overlay/Momentum Toolkit indicators, so a ticker's
score here should match what Drew would read by hand on the chart.
"""
import numpy as np
import pandas as pd

import config


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Check 1 & 2 inputs: EMA stack
    df["ema9"] = df["close"].ewm(span=config.EMA_9, adjust=False).mean()
    df["ema20"] = df["close"].ewm(span=config.EMA_20, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=config.EMA_200, adjust=False).mean()

    # Check 3 input: MACD (line above/below signal)
    ema_fast_macd = df["close"].ewm(span=config.MACD_FAST, adjust=False).mean()
    ema_slow_macd = df["close"].ewm(span=config.MACD_SLOW, adjust=False).mean()
    df["macd"] = ema_fast_macd - ema_slow_macd
    df["macd_signal"] = df["macd"].ewm(span=config.MACD_SIGNAL, adjust=False).mean()

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
