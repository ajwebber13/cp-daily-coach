# CP Daily Coach

Answers 4 questions every day: **Buy? Sell? Hold? Do nothing?**

No ML, no broker API, no automation of trades. It scans the S&P 500, scores
every ticker with plain rules, and posts BUY / SELL / HOLD signals to
Discord. You still pull the trigger yourself.

Separate project from `cp-stock-signal-engine` (live ML system) and
`cp-rules-backtest` (the trend-following backtest that showed automation
wasn't worth it yet). This is the coach — a decision-support tool, not a
trading system.

Three checks, three purposes:
- **`premarket.py`** (before open, ~6:00 AM ET) — re-runs your 6-check
  (minus Volume — too thin pre-market to compare) using the current
  pre-market price. Shows which tickers are already clearing the
  checklist before the bell. Not a BUY signal — an early read using an
  estimated price, confirm against `scan.py` after close.
- **`midday.py`** (midday, ~12 PM ET) — lightweight movers check (3%+
  moves), separate from the checklist scoring. No BUY/SELL/HOLD, just
  what's moving so far today.
- **`scan.py`** (after close, ~4-5 PM ET) — the main event. Full
  BUY/SELL/HOLD/DO NOTHING signals with entry/stop/target and a
  confidence score, checked against market trend, reward:risk, and
  earnings timing.

## Setup

```bash
pip install -r requirements.txt
```

Set your Discord webhook (same one your other alerts use, or a new
`#cp-stock-coach` channel — your call):

```powershell
$env:DISCORD_WEBHOOK_URL = "your_webhook_url"
```

(Set this permanently as a Windows environment variable, or a GitHub Actions
secret if you later automate the run — see below.)

## Run it

```bash
python scan.py
```

The S&P 500 ticker list comes from a static CSV bundled with the repo
(`sp500_static.csv`) — no network call needed on a normal run. It goes
stale slowly (a handful of index changes a year); refresh it every few
months with `python universe.py --refresh`, which pulls a fresh list and
falls back to the existing static file if the refresh fails for any
reason. It's not refreshed automatically.

Each run pulls ~300 days of price history per ticker in batches — takes a
couple minutes. Posts results to Discord (or prints to your terminal if
`DISCORD_WEBHOOK_URL` isn't set).

## Tracking positions

The coach doesn't know what you actually bought unless you tell it. When you
enter a trade:

```bash
python positions.py add NVDA 192.35
```

That ticker will now show up as HOLD (with a suggested trailing stop) or
SELL (if the trend flips or your stop gets hit) instead of BUY, until you
remove it:

```bash
python positions.py remove NVDA
python positions.py list
```

`add` and `remove` automatically commit and push `positions.json` right
after saving it, so the cloud-scheduled scan (which starts from a fresh
checkout every run) sees it on its next run. If git isn't available or
the push fails for any reason, it saves locally and prints a warning
telling you to push manually — it never blocks you from recording the
trade.

## Outcome tracking

Every BUY/PUT WATCH signal that gets posted is logged to
`signals_log.jsonl` (date, ticker, signal, score, entry, stop, target,
reward:risk) — see `signals_log.py`. This is the coach's only record of
what it actually told you to consider, and the only way to answer "does
this thing work?"

`grade_signals.py` grades each logged signal once it's at least 5 trading
days old, checking the price history since it posted to see whether
target or stop was touched first. Outcomes:

| Outcome | Meaning |
|---|---|
| `hit_target` | Target touched before stop |
| `hit_stop` | Stop touched before target (or both same day — daily bars can't tell which came first, so this is the conservative call) |
| `expired_flat` | Neither touched within 20 trading days |
| `open` | At least 5 trading days old, still under 20, nothing touched yet |

Results go to a separate `signals_outcomes.jsonl` (keyed by
date+ticker+signal) rather than rewriting the raw log, so grading can
never corrupt the original record. A weekly workflow
(`.github/workflows/grade-signals.yml`, Sundays) runs the grader and
posts a hit-rate / average-R rollup to Discord, split by BUY vs
PUT WATCH.

Signal tracking starts from whenever this was added — there's no
history to backfill from before it (the raw entry/stop/target values
only ever existed in the Discord message itself, which nothing else
recorded).

## AI reasoning (optional)

Adds a 2-3 sentence plain-language explanation under each BUY/HOLD/SELL
pick, using Google Gemini's free tier. The rules still decide the signal —
this only explains why, so you don't have to read the score breakdown
yourself. Only called on the picks that already cleared the rules (top 15
BUY + anything held), not the full 500-ticker universe, to stay
comfortably inside the free tier's rate limits.

1. Get a free key: [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no credit card needed.
2. Set it locally:
```powershell
[System.Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'your_key_here', 'User')
```

For GitHub Actions, add `GEMINI_API_KEY` as a repo secret the same way you
added `DISCORD_WEBHOOK_URL`, then it's already wired into both workflow
files' `env:` blocks.

If `GEMINI_API_KEY` isn't set, the coach runs exactly as before —
rules-only, no reasoning line, no error.

## How the score works

This is Drew's TradingView 6-check swing system, automated — same rules,
same math, so a ticker's score here should match what you'd get checking
the chart by hand. 0-100, five pass/fail checks worth 20 points each (see
`scorer.py` for the exact math):

| Check | Points | What it checks |
|---|---|---|
| Trend | 20 | Price above EMA 200? |
| Crossover | 20 | EMA 9 above EMA 20? |
| MACD | 20 | MACD line above its signal line? |
| RSI | 20 | RSI inside the 40-65 zone? |
| Volume | 20 | Today's volume above the 20-day average? |

A 6th check — **ATR** — is informational only, not scored. It's used to
size the stop (`entry - 2x ATR`) and target (`entry + 3x ATR`), same as
you do reading it off the chart.

A BUY signal requires trend alignment (checks 1 and 2 both true) **and**
a score of 70+ (`config.py` → `BUY_SCORE_MIN`, so at least 4 of 5 checks
passing). Every check is pass/fail — no partial credit for "almost." A
100 means all 5 scored checks are true right now, not a 100% chance of
being right.

**Not automated by this script:** support/resistance levels and
candlestick patterns (BE, SS, MS, ES) — those still need your eyes on
the chart.

## Automating the daily run (GitHub Actions — recommended)

Runs automatically on GitHub's servers, no need to keep your own PC on.

1. Create a new GitHub repo (private is fine) and push these files to it,
   including the `.github/workflows/daily-scan.yml` file.
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DISCORD_WEBHOOK_URL`
   - Value: your webhook URL
3. That's it. It runs weekdays at 20:30/21:30 UTC (4:30 PM ET, after
   market close — two cron lines cover both daylight saving and standard
   time) and posts straight to Discord. Change the `cron` lines in the
   workflow file if you want a different time.
4. To test it immediately instead of waiting: go to the **Actions** tab →
   **Daily Stock Coach** → **Run workflow**.

`positions.json` and `signals_log.jsonl` get committed back to the repo
automatically after each run, so HOLD/SELL tracking and signal history
both persist between runs.

## Automating the daily run (Windows Task Scheduler — local alternative)

Windows Task Scheduler, daily after market close:
```powershell
schtasks /create /tn "CP Daily Coach" /tr "python C:\path\to\scan.py" /sc daily /st 16:30
```

## Files

```
config.py           - all tunable settings (weights, thresholds, universe)
universe.py          - loads the S&P 500 ticker list (static, optional --refresh)
indicators.py        - EMA/MACD/RSI/ATR/volume calculations
scorer.py            - confidence scoring + BUY/SELL/HOLD/PUT WATCH/DO NOTHING logic
market_regime.py     - checks SPY/QQQ trend, raises the bar in a weak market
earnings_check.py    - skips candidates with earnings coming up soon
options_overlay.py   - suggests a liquid call/put contract for BUY/PUT WATCH picks
ai_reasoning.py       - optional plain-language explanation via Gemini
positions.py          - tracks what you're actually holding
signals_log.py         - logs every posted BUY/PUT WATCH signal for later grading
grade_signals.py        - grades logged signals, posts a weekly hit-rate rollup
discord_alert.py         - formats and sends messages, coverage canary
scan.py                   - main entry point, run this daily (after close)
premarket.py               - 6-check pre-market watch list, run before open
midday.py                   - midday movers check-in
test_synthetic.py            - scorer/positions sanity check, no network needed
test_grade_signals.py         - grade_signals sanity check, no network needed
```

## Disclaimer

Educational tool, not financial advice. The scoring logic is unvalidated —
consider backtesting the entry criteria (same approach as
`cp-rules-backtest`) before trusting the BUY signals with real money.
