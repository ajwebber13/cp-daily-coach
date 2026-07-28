"""
config.py
All tunable settings for the Daily Stock Coach.
"""
import os

# --- Universe ---
# S&P 500, scanned fresh each run (cached locally, see universe.py)
UNIVERSE_SOURCE = "sp500"
UNIVERSE_CACHE_FILE = "sp500_tickers.csv"
UNIVERSE_CACHE_DAYS = 7          # re-scrape the constituent list at most weekly

# --- Data ---
LOOKBACK_DAYS = 300              # enough history for a 200-day SMA + buffer
BATCH_SIZE = 100                 # tickers per yfinance batch download

# --- Indicators ---
EMA_FAST = 20
EMA_SLOW = 50
SMA_TREND = 200
ATR_PERIOD = 14
RSI_PERIOD = 14
RELVOL_PERIOD = 20

# --- Signal thresholds ---
BUY_SCORE_MIN = 70               # confidence score needed to flag a BUY
TOP_N_RESULTS = 15               # how many BUY candidates to show, ranked by score

# --- Earnings avoidance (Upgrade #5) ---
# Skip a BUY if earnings land within this many days — a surprise can gap
# the stock past its stop-loss overnight. Only checked on candidates that
# already passed every other filter (see earnings_check.py).
EARNINGS_AVOID_DAYS = 7
EARNINGS_CHECK_POOL = 30         # how many top-scoring candidates get checked before taking the final top 15

# --- Market regime (Upgrade #1: don't fight the tape) ---
MARKET_MIXED_PENALTY = 5         # added to BUY_SCORE_MIN when SPY/QQQ disagree
MARKET_BEARISH_PENALTY = 10      # added to BUY_SCORE_MIN when both are trending down

# --- Entry / stop / target ---
ATR_STOP_MULT = 2.0
ATR_TARGET_MULT = 3.0            # gives roughly 1.5:1 reward-to-risk (see scorer.py)

# --- Risk/reward gate (Upgrade #2) ---
# Even if a ticker scores well, skip it if the reward doesn't clearly
# justify the risk. 3xATR target / 2xATR stop already gives ~1.5:1 by
# construction, so this mostly catches edge cases where volatility
# distorts that ratio.
MIN_REWARD_RISK_RATIO = 1.5

# --- Scoring weights (must sum to 100) ---
# Rebalanced again for Upgrade #4 (sector strength) — took a bit from
# trend/volume/RSI rather than disturbing support/resistance again.
WEIGHT_TREND = 30
WEIGHT_VOLUME = 12
WEIGHT_RSI = 13
WEIGHT_VOLATILITY = 15
WEIGHT_SUPPORT_RESISTANCE = 20
WEIGHT_SECTOR = 10

# --- Position tracking ---
POSITIONS_FILE = "positions.json"

# --- Pre-market movers ---
PREMARKET_MOVE_THRESHOLD = 3.0    # minimum % move (up or down) to flag a ticker
PREMARKET_TOP_N = 15              # gainers and losers shown, each

# --- Discord ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# --- AI reasoning (optional) ---
# Adds a plain-language explanation to each BUY/HOLD/SELL pick. Only called
# on tickers that already cleared the rule-based signal — not the full
# universe — to keep this comfortably inside Gemini's free tier. If
# GEMINI_API_KEY isn't set, the coach just skips this and runs rules-only.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")  # free-tier model
AI_REASONING_ENABLED = bool(GEMINI_API_KEY)
