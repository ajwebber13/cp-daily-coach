"""
chart_image.py
Renders a candlestick PNG (last CHART_IMAGE_BARS bars, EMA 9/20/50/200
overlay, RSI panel) for a signal using mplfinance. Optional — only runs
when config.CHART_IMAGES is True, and only for the top CHART_IMAGE_TOP_N
signals by score (see scan.py), since rendering + uploading a chart adds
real time per signal.
"""
import io

import config


def render_chart(df, ticker: str, title: str = None) -> bytes:
    """
    df: indicator-enriched OHLCV dataframe (indicators.add_indicators()
        already applied), with enough history that EMA 200 has settled
        even though only the last CHART_IMAGE_BARS bars are plotted.
    Returns PNG bytes, or None if mplfinance isn't installed or rendering
    fails for any reason — a chart image is a nice-to-have, never worth
    failing the scan or dropping the signal's text card over.
    """
    try:
        import mplfinance as mpf
    except ImportError:
        print("mplfinance not installed — skipping chart image. Run: pip install mplfinance")
        return None

    try:
        plot_df = df.tail(config.CHART_IMAGE_BARS).copy()
        plot_df.index.name = "Date"
        plot_df = plot_df.rename(columns={
            "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
        })

        addplots = [
            mpf.make_addplot(plot_df["ema9"], color="#2196f3", width=0.8),
            mpf.make_addplot(plot_df["ema20"], color="#ff9800", width=0.8),
            mpf.make_addplot(plot_df["ema50"], color="#9c27b0", width=0.8),
            mpf.make_addplot(plot_df["ema200"], color="#f44336", width=1.0),
            mpf.make_addplot(plot_df["rsi"], panel=1, color="#4caf50", ylabel="RSI"),
        ]

        buf = io.BytesIO()
        mpf.plot(
            plot_df[["Open", "High", "Low", "Close", "Volume"]],
            type="candle",
            style="yahoo",
            addplot=addplots,
            volume=False,
            panel_ratios=(3, 1),
            title=title or ticker,
            savefig=dict(fname=buf, format="png", dpi=110, bbox_inches="tight"),
        )
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"  {ticker}: chart image render failed — {e}")
        return None
