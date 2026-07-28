"""
test_synthetic.py
Sanity check for scorer.py and positions.py using fake price data — no
network needed. Confirms the scoring math and BUY/SELL/HOLD logic run
without errors before you point this at real S&P 500 data.
"""
import os

import numpy as np
import pandas as pd

import config
from indicators import add_indicators
from scorer import evaluate_ticker
import positions


def make_fake_ticker(seed: int, n_days: int = 300, start_price: float = 100.0, uptrend: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-01", periods=n_days)
    drift = 0.0006 if uptrend else -0.0006
    daily_returns = rng.normal(loc=drift, scale=0.012, size=n_days)
    close = start_price * np.cumprod(1 + daily_returns)
    high = close * (1 + np.abs(rng.normal(0, 0.005, n_days)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n_days)))
    open_ = close * (1 + rng.normal(0, 0.002, n_days))
    volume = rng.integers(1_000_000, 3_000_000, n_days).astype(float)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)
    return df


def main():
    # Clean slate for the test
    if os.path.exists(config.POSITIONS_FILE):
        os.remove(config.POSITIONS_FILE)

    uptrend_df = add_indicators(make_fake_ticker(seed=1, uptrend=True))
    downtrend_df = add_indicators(make_fake_ticker(seed=2, uptrend=False))

    print("=== Not held, uptrend ticker ===")
    result = evaluate_ticker("FAKE_UP", uptrend_df.iloc[-1], held_position=None)
    print(result)
    assert result["signal"] in ("BUY", "DO NOTHING")
    if result["signal"] == "BUY":
        assert result["stop"] < result["entry"] < result["target"]

    print("\n=== Not held, downtrend ticker ===")
    result = evaluate_ticker("FAKE_DOWN", downtrend_df.iloc[-1], held_position=None)
    print(result)
    assert result["signal"] == "DO NOTHING", "Downtrend should never trigger a BUY"

    print("\n=== Held position, check HOLD/SELL logic ===")
    positions.add_position("FAKE_UP", entry_price=uptrend_df["close"].iloc[-30], stop_price=uptrend_df["close"].iloc[-30] * 0.9)
    positions.update_highest_close("FAKE_UP", uptrend_df["close"].iloc[-1])
    held = positions.list_positions()
    result = evaluate_ticker("FAKE_UP", uptrend_df.iloc[-1], held_position=held["FAKE_UP"])
    print(result)
    assert result["signal"] in ("HOLD", "SELL")

    print("\nAll sanity checks passed.")

    # cleanup
    if os.path.exists(config.POSITIONS_FILE):
        os.remove(config.POSITIONS_FILE)


if __name__ == "__main__":
    main()
