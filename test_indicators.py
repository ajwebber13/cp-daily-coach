"""
test_indicators.py
Sanity check for indicators.py's support/resistance finder and
candlestick pattern detection, using hand-built OHLC data — no network
needed. Each candlestick test isolates exactly one pattern to make sure
the shape rules don't cross-fire on each other.
"""
import pandas as pd

from indicators import (
    find_support_resistance,
    detect_candlestick_patterns,
    describe_candlestick_patterns,
    levels_caution,
)


def bars(rows: list) -> pd.DataFrame:
    """rows: list of (open, high, low, close) tuples, oldest first."""
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1_000_000.0} for o, h, l, c in rows],
        index=pd.bdate_range("2026-01-05", periods=len(rows)),
    )


def make_swing_df() -> pd.DataFrame:
    """
    21 hand-built bars with two deliberate swing highs (110 @ idx3,
    111 @ idx13) and two deliberate swing lows (93 @ idx8, 94 @ idx18),
    each confirmed by a 2-bar rise/fall on both sides (order=2).
    """
    highs = [100, 102, 105, 110, 106, 103, 100, 97, 94, 96, 99, 103, 107, 111, 108, 105, 101, 98, 95, 97, 100]
    lows = [x - 1 for x in highs]
    rows = [(h - 0.5, h, l, h - 0.5) for h, l in zip(highs, lows)]
    return bars(rows)


def test_support_resistance_nearest_levels():
    df = make_swing_df()
    result = find_support_resistance(df, current_price=100, order=2)
    assert result["resistance"] == [110.0, 111.0]
    assert result["support"] == [94.0, 93.0]


def test_support_resistance_range_fields():
    df = make_swing_df()
    result = find_support_resistance(df, current_price=100, order=2)
    assert result["low_20d"] == round(float(df.tail(20)["low"].min()), 2)
    assert result["high_20d"] == round(float(df.tail(20)["high"].max()), 2)
    assert result["low_52w"] == round(float(df.tail(252)["low"].min()), 2)
    assert result["high_52w"] == round(float(df.tail(252)["high"].max()), 2)


def test_doji():
    df = bars([(100, 102, 98, 100.05)])
    patterns = detect_candlestick_patterns(df)
    assert patterns["doji"] is True
    assert patterns["hammer"] is False
    assert patterns["shooting_star"] is False


def test_hammer():
    df = bars([(100, 101.2, 95, 101)])
    patterns = detect_candlestick_patterns(df)
    assert patterns["hammer"] is True
    assert patterns["doji"] is False
    assert patterns["shooting_star"] is False


def test_shooting_star():
    df = bars([(101, 106, 99.8, 100)])
    patterns = detect_candlestick_patterns(df)
    assert patterns["shooting_star"] is True
    assert patterns["doji"] is False
    assert patterns["hammer"] is False


def test_bullish_engulfing():
    df = bars([
        (105, 106, 99, 100),   # prev: bearish
        (99, 107, 98, 106),    # curr: bullish, engulfs prev's body
    ])
    patterns = detect_candlestick_patterns(df)
    assert patterns["bullish_engulfing"] is True
    assert patterns["bearish_engulfing"] is False


def test_bearish_engulfing():
    df = bars([
        (100, 106, 99, 105),   # prev: bullish
        (106, 107, 98, 99),    # curr: bearish, engulfs prev's body
    ])
    patterns = detect_candlestick_patterns(df)
    assert patterns["bearish_engulfing"] is True
    assert patterns["bullish_engulfing"] is False


def test_close_above_prior_high():
    df = bars([
        (95, 100, 94, 98),     # prev: bullish, high = 100
        (99, 103, 98, 102),    # curr: close (102) > prev high (100)
    ])
    patterns = detect_candlestick_patterns(df)
    assert patterns["close_above_prior_high"] is True
    # isolated from engulfing: prev is bullish, so bullish_engulfing needs
    # a bearish prev and can't fire here; curr is bullish so bearish_engulfing can't either
    assert patterns["bullish_engulfing"] is False
    assert patterns["bearish_engulfing"] is False


def test_single_bar_has_no_two_bar_patterns():
    df = bars([(100, 101.2, 95, 101)])  # the hammer bar, alone
    patterns = detect_candlestick_patterns(df)
    assert patterns["bullish_engulfing"] is False
    assert patterns["bearish_engulfing"] is False
    assert patterns["close_above_prior_high"] is False
    assert patterns["hammer"] is True  # single-bar reads still work


def test_levels_caution_buy_resistance_near_entry():
    msg = levels_caution("BUY", entry=100, target=100.3, atr=1.0,
                          resistance=[100.5], support=[], low_52w=50, high_52w=200)
    assert msg == "Levels: resistance $100.5 within 0.50 ATR of entry"


def test_levels_caution_buy_target_above_resistance():
    msg = levels_caution("BUY", entry=100, target=110, atr=1.0,
                          resistance=[105], support=[], low_52w=50, high_52w=200)
    assert msg == "Levels: target above nearest resistance ($105)"


def test_levels_caution_buy_target_above_52w_high():
    msg = levels_caution("BUY", entry=100, target=120, atr=1.0,
                          resistance=[], support=[], low_52w=50, high_52w=115)
    assert msg == "Levels: target above 52w high"


def test_levels_caution_buy_no_trigger():
    msg = levels_caution("BUY", entry=100, target=105, atr=1.0,
                          resistance=[110], support=[], low_52w=50, high_52w=200)
    assert msg is None


def test_levels_caution_put_watch_support_near_entry():
    msg = levels_caution("PUT WATCH", entry=100, target=99.7, atr=1.0,
                          resistance=[], support=[99.5], low_52w=50, high_52w=200)
    assert msg == "Levels: support $99.5 within 0.50 ATR of entry"


def test_levels_caution_put_watch_target_below_support():
    msg = levels_caution("PUT WATCH", entry=100, target=90, atr=1.0,
                          resistance=[], support=[95], low_52w=50, high_52w=200)
    assert msg == "Levels: target below nearest support ($95)"


def test_levels_caution_put_watch_target_below_52w_low():
    msg = levels_caution("PUT WATCH", entry=100, target=80, atr=1.0,
                          resistance=[], support=[], low_52w=85, high_52w=200)
    assert msg == "Levels: target below 52w low"


def test_levels_caution_put_watch_no_trigger():
    msg = levels_caution("PUT WATCH", entry=100, target=95, atr=1.0,
                          resistance=[], support=[90], low_52w=50, high_52w=200)
    assert msg is None


def test_levels_caution_combines_multiple_reasons():
    msg = levels_caution("BUY", entry=100, target=250, atr=1.0,
                          resistance=[100.5, 200], support=[], low_52w=50, high_52w=240)
    assert msg == (
        "Levels: resistance $100.5 within 0.50 ATR of entry; "
        "target above nearest resistance ($100.5); "
        "target above 52w high"
    )


def test_describe_candlestick_patterns():
    patterns = {"doji": False, "hammer": True, "shooting_star": False,
                "bullish_engulfing": True, "bearish_engulfing": False,
                "close_above_prior_high": False}
    labels = describe_candlestick_patterns(patterns)
    assert labels == ["Bullish engulfing", "Hammer"]


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} indicators sanity checks passed.")


if __name__ == "__main__":
    main()
