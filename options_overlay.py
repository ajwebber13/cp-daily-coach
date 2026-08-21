"""
options_overlay.py
Adds an options lens to BUY and PUT WATCH candidates from scan.py: a
liquid contract suggestion, and a cheap/expensive volatility read.

BUY -> calls. PUT WATCH -> puts.

Real IV percentile and delta need a paid data feed (Tradier, Polygon,
CBOE) — yfinance doesn't expose those free. This uses realized volatility
as a proxy for "cheap vs expensive" (labeled as such, not real IV), and
moneyness (% OTM) instead of delta for strike selection.
"""
import time
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

import config


def get_realized_vol_read(ticker: str) -> dict:
    """Realized-vol percentile vs its own 1-year range. Proxy for IV, not IV."""
    hist = yf.Ticker(ticker).history(period="1y")
    if hist.empty or len(hist) < config.OPTIONS_VOL_LOOKBACK_DAYS + 5:
        return {"available": False}

    log_ret = np.log(hist["Close"] / hist["Close"].shift(1))
    rolling_vol = log_ret.rolling(config.OPTIONS_VOL_LOOKBACK_DAYS).std() * np.sqrt(252)
    rolling_vol = rolling_vol.dropna()
    if rolling_vol.empty:
        return {"available": False}

    current = rolling_vol.iloc[-1]
    percentile = (rolling_vol < current).mean() * 100
    return {
        "available": True,
        "percentile_1y": round(float(percentile), 1),
        "read": "expensive" if percentile > 65 else "cheap" if percentile < 35 else "normal",
    }


def pick_expiry(tk: yf.Ticker) -> str | None:
    today = datetime.now().date()
    best_expiry, best_diff = None, None
    for exp_str in tk.options:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        dte = (exp_date - today).days
        if config.OPTIONS_TARGET_DTE_MIN <= dte <= config.OPTIONS_TARGET_DTE_MAX:
            mid = (config.OPTIONS_TARGET_DTE_MIN + config.OPTIONS_TARGET_DTE_MAX) / 2
            diff = abs(dte - mid)
            if best_diff is None or diff < best_diff:
                best_expiry, best_diff = exp_str, diff
    return best_expiry


def _pick_contract(chain_side, target_strike: float) -> dict | None:
    """Shared liquidity + drift filtering for either calls or puts."""
    chain_side = chain_side.copy()
    chain_side["strike_dist"] = (chain_side["strike"] - target_strike).abs()
    chain_side["spread_pct"] = (
        (chain_side["ask"] - chain_side["bid"]) / chain_side[["bid", "ask"]].mean(axis=1)
    )

    liquid = chain_side[
        (chain_side["openInterest"] >= config.OPTIONS_MIN_OPEN_INTEREST)
        & (chain_side["spread_pct"] <= config.OPTIONS_MAX_SPREAD_PCT)
    ].sort_values("strike_dist")

    if liquid.empty:
        return None

    best = liquid.iloc[0]

    # Reject it if the closest liquid strike is still way off target —
    # better to show no contract than a deep ITM/OTM one that doesn't
    # match what the target moneyness was supposed to mean.
    max_drift = target_strike * config.OPTIONS_MAX_STRIKE_DRIFT_PCT
    if best["strike_dist"] > max_drift:
        return None

    return {
        "strike": float(best["strike"]),
        "bid": float(best["bid"]),
        "ask": float(best["ask"]),
        "open_interest": int(best["openInterest"]),
        "spread_pct": round(float(best["spread_pct"]) * 100, 1),
    }


def pick_call_contract(tk: yf.Ticker, expiry: str, entry_price: float) -> dict | None:
    calls = tk.option_chain(expiry).calls
    target_strike = entry_price * (1 + config.OPTIONS_TARGET_MONEYNESS)
    return _pick_contract(calls, target_strike)


def pick_put_contract(tk: yf.Ticker, expiry: str, entry_price: float) -> dict | None:
    puts = tk.option_chain(expiry).puts
    target_strike = entry_price * (1 - config.OPTIONS_TARGET_MONEYNESS)
    return _pick_contract(puts, target_strike)


def add_options_to_candidate(candidate: dict) -> dict:
    """
    Mutates a BUY or PUT WATCH candidate dict (from scorer.evaluate_ticker)
    in place, adding an 'options' key. Safe to call even if options data
    isn't available — just sets options=None and moves on.
    """
    ticker = candidate["ticker"]
    is_bullish = candidate["signal"] == "BUY"
    pick_fn = pick_call_contract if is_bullish else pick_put_contract
    label = "call" if is_bullish else "put"

    try:
        tk = yf.Ticker(ticker)
        expiry = pick_expiry(tk)
        if not expiry:
            print(f"  {ticker}: no expiry found in target DTE window "
                  f"(tk.options returned {len(tk.options)} dates)")
            candidate["options"] = None
            return candidate

        contract = pick_fn(tk, expiry, candidate["entry"])
        if not contract:
            print(f"  {ticker}: expiry {expiry} found, but no {label} cleared "
                  f"the OI/spread filter")
            candidate["options"] = None
            return candidate

        vol_read = get_realized_vol_read(ticker)
        candidate["options"] = {"expiry": expiry, "volatility": vol_read, **contract}
        print(f"  {ticker}: {label} OK — ${contract['strike']} strike, "
              f"OI {contract['open_interest']}")
    except Exception as e:
        print(f"  {ticker}: options lookup FAILED — {e}")
        candidate["options"] = None

    return candidate


def add_options_to_results(candidates: list) -> None:
    """In-place, same pattern as ai_reasoning.add_reasoning_to_results.
    Handles both BUY and PUT WATCH candidates."""
    for c in candidates:
        if c.get("signal") in ("BUY", "PUT WATCH"):
            add_options_to_candidate(c)
            time.sleep(1.5)  # space out requests, Yahoo throttles rapid-fire calls
