"""
config.py
All tunable settings for the Daily Stock Coach.
"""
import os

# --- Data ---
LOOKBACK_DAYS = 300              # enough history for a 200-day SMA + buffer
BATCH_SIZE = 100                 # tickers per yfinance batch download

# --- Indicators ---
# Matches Drew's TradingView 6-check swing checklist exactly.
EMA_9 = 9
EMA_20 = 20
EMA_200 = 200
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
RSI_PERIOD = 14
RSI_ZONE_MIN = 40
RSI_ZONE_MAX = 65
RELVOL_PERIOD = 20

# --- Signal thresholds ---
BUY_SCORE_MIN = 70               # confidence score needed to flag a BUY
TOP_N_RESULTS = 15               # how many BUY candidates to show, ranked by score

PUT_SCORE_MIN = 70               # confidence score needed to flag a PUT WATCH
TOP_N_PUT_RESULTS = 15           # how many PUT WATCH candidates to show, ranked by score

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
# Replaced with Drew's TradingView 6-check swing system (2026-08-20).
# 5 scored checks, 20pts max each. ATR is the 6th check but is
# informational only (used for stop/target sizing below, not for the
# score itself) — same as how Drew reads it on the chart.
WEIGHT_TREND = 20        # Check 1: price above EMA 200
WEIGHT_CROSSOVER = 20    # Check 2: EMA 9 above EMA 20
WEIGHT_MACD = 20         # Check 3: MACD line above signal line
WEIGHT_RSI = 20          # Check 4: RSI in the 40-65 zone
WEIGHT_VOLUME = 20       # Check 5: today's volume above 20-day average

# --- Marginal-pass grading (2026-08-20) ---
# A check that barely passes isn't as strong as one that passes clean —
# same distinction Drew makes reading the chart by hand ("RSI near
# ceiling", "crossover too tight"). Each check below can score full
# marks, half marks (marginal, flagged), or zero (failed).
TREND_MARGIN_PCT = 0.01          # need price > 1% above EMA200 for full marks
CROSSOVER_MARGIN_PCT = 0.005     # need EMA9 > 0.5% above EMA20 for full marks
MACD_MARGIN_PCT = 0.0005         # need MACD-signal gap > 0.05% of price for full marks
RSI_SWEET_MIN = 45               # full marks inside 45-60, half marks 40-45 / 60-65
RSI_SWEET_MAX = 60
VOLUME_IDEAL_MAX = 3.0           # full marks 1.0-3.0x, half marks above 3.0x (spike, flagged)

# --- Position tracking ---
POSITIONS_FILE = "positions.json"

# --- Pre-market movers ---
PREMARKET_MOVE_THRESHOLD = 3.0    # minimum % move (up or down) to flag a ticker
PREMARKET_TOP_N = 15              # gainers and losers shown, each

# --- Options overlay ---
OPTIONS_OVERLAY_ENABLED = True
OPTIONS_MIN_OPEN_INTEREST = 500
OPTIONS_MAX_SPREAD_PCT = 0.10
OPTIONS_TARGET_DTE_MIN = 30
OPTIONS_TARGET_DTE_MAX = 45
OPTIONS_TARGET_MONEYNESS = 0.05
OPTIONS_MAX_STRIKE_DRIFT_PCT = 0.05   # reject if closest liquid strike is >5% of target away
OPTIONS_VOL_LOOKBACK_DAYS = 30

# --- Outcome tracking ---
# Every BUY/PUT WATCH shown to Discord gets appended to SIGNALS_LOG_FILE
# (see signals_log.py). grade_signals.py later checks whether each one
# hit its target, hit its stop, or expired flat, and writes the result to
# SIGNALS_OUTCOMES_FILE (kept separate so the raw log stays append-only).
SIGNALS_LOG_FILE = "signals_log.jsonl"
SIGNALS_OUTCOMES_FILE = "signals_outcomes.jsonl"
GRADE_MIN_DAYS = 5    # don't bother grading a signal until it's at least this many trading days old
GRADE_MAX_DAYS = 20   # ungraded past this many trading days without hitting target/stop -> expired_flat

# --- Data-health canary ---
# Shown at the top of every Discord post so a data outage looks different
# from a genuinely quiet day instead of producing an identical "nothing
# to report" message.
COVERAGE_WARN_PCT = 90

# --- Discord ---
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# --- AI reasoning (optional) ---
# Adds a plain-language explanation to each BUY/HOLD/SELL pick. Only called
# on tickers that already cleared the rule-based signal — not the full
# universe — to keep this comfortably inside Gemini's free tier. If
# GEMINI_API_KEY isn't set, the coach just skips this and runs rules-only.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")  # free-tier model
AI_REASONING_ENABLED = bool(GEMINI_API_KEY)
