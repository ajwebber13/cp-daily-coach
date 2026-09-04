"""
market_regime.py
"Don't fight the tape." Checks whether the overall market (SPY and QQQ) is
trending up or down, and adjusts how selective the scanner is:
  - Market trending up  -> normal bar for a BUY signal
  - Market mixed        -> slightly higher bar
  - Market trending down -> much higher bar (fewer, stronger-only picks)

This doesn't predict the market — it just avoids fighting an obvious
downtrend by demanding a stronger individual setup when conditions are
already working against you.
"""
import config
from indicators import add_indicators
from scorer import trend_aligned


def _is_bullish(ticker_df) -> bool:
    latest = ticker_df.iloc[-1]
    return trend_aligned(latest)


def get_market_regime() -> dict:
    """
    Returns:
        {
            "regime": "bullish" | "neutral" | "bearish",
            "spy_bullish": bool,
            "qqq_bullish": bool,
            "score_adjustment": int,  # added to BUY_SCORE_MIN
            "label": str,             # human-readable, for the Discord header
        }
    Falls back to "neutral" (no adjustment) if data can't be fetched —
    a missing market check should never block the whole scan.
    """
    try:
        import yfinance as yf
        raw = yf.download(
            ["SPY", "QQQ"], period=f"{config.LOOKBACK_DAYS}d",
            group_by="ticker", auto_adjust=True, threads=True, progress=False,
        )

        spy = add_indicators(raw["SPY"].rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna())
        qqq = add_indicators(raw["QQQ"].rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna())

        spy_bullish = _is_bullish(spy)
        qqq_bullish = _is_bullish(qqq)

    except Exception as e:
        print(f"Market regime check failed ({e}). Defaulting to neutral (no adjustment).")
        return {
            "regime": "neutral", "spy_bullish": None, "qqq_bullish": None,
            "score_adjustment": 0,
            "label": "Unknown (check skipped)",
        }

    if spy_bullish and qqq_bullish:
        return {
            "regime": "bullish", "spy_bullish": True, "qqq_bullish": True,
            "score_adjustment": 0,
            "label": "🟢 Market is trending up (SPY & QQQ both healthy)",
        }
    elif not spy_bullish and not qqq_bullish:
        return {
            "regime": "bearish", "spy_bullish": False, "qqq_bullish": False,
            "score_adjustment": config.MARKET_BEARISH_PENALTY,
            "label": "🔴 Market is trending down (SPY & QQQ both weak) — being extra picky today",
        }
    else:
        return {
            "regime": "neutral", "spy_bullish": spy_bullish, "qqq_bullish": qqq_bullish,
            "score_adjustment": config.MARKET_MIXED_PENALTY,
            "label": "🟡 Market is mixed (SPY and QQQ disagree) — being a bit more picky today",
        }
