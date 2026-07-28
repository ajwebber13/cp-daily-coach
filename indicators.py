"""
indicators.py
Computes the 5 inputs the coach uses: 20 EMA, 50 EMA, 200 SMA, ATR, and
relative volume. Same math as the backtest engine, kept separate here so
this project doesn't depend on cp-rules-backtest.
"""
import numpy as np
import pandas as pd

import config


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["sma_trend"] = df["close"].rolling(config.SMA_TREND).mean()
    df["ema_fast"] = df["close"].ewm(span=config.EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=config.EMA_SLOW, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)

    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / config.ATR_PERIOD, adjust=False).mean()
    df["atr_pct"] = df["atr"] / df["close"]  # volatility relative to price, for cross-ticker comparison

    df["vol_avg"] = df["volume"].rolling(config.RELVOL_PERIOD).mean()
    df["rel_vol"] = df["volume"] / df["vol_avg"]

    return df
