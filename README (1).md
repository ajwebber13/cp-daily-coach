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
- **`premarket.py`** (before open, ~7-8 AM ET) — awareness only, no scoring.
  Flags any S&P 500 ticker moving 3%+ before the bell.
- **`midday.py`** (midday, ~12 PM ET) — same lightweight movers check,
  partway through the trading day.
- **`scan.py`** (after close, ~4-5 PM ET) — the main event. Full
  BUY/SELL/HOLD/DO NOTHING signals with entry/stop/target and a
  confidence score, checked against market trend, reward:risk, resistance,
  sector strength, and earnings timing.

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

First run downloads and caches the S&P 500 list (~500 tickers, re-checked
weekly), then pulls ~300 days of price history for each in batches. Takes a
couple minutes the first time. Posts results to Discord (or prints to your
terminal if `DISCORD_WEBHOOK_URL` isn't set).

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

0-100, four rule-based components (see `scorer.py` for the exact math):

| Component | Points | What it checks |
|---|---|---|
| Trend | 40 | Price above 200 SMA, 20 EMA above 50 EMA |
| Volume | 20 | Today's volume vs. 20-day average |
| RSI | 20 | Momentum in a healthy zone (peaks at RSI 55) |
| Volatility | 20 | ATR relative to price — calmer stocks score higher |

A BUY signal requires trend alignment **and** a score of 70+
(`config.py` → `BUY_SCORE_MIN`). This is a ranking heuristic, not a
probability — a 92 means 92% of the defined conditions are met, not a 92%
chance of being right.

## Automating the daily run (GitHub Actions — recommended)

Runs automatically on GitHub's servers, no need to keep your own PC on.

1. Create a new GitHub repo (private is fine) and push these files to it,
   including the `.github/workflows/daily-scan.yml` file.
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DISCORD_WEBHOOK_URL`
   - Value: your webhook URL
3. That's it. It runs weekdays at 21:00 UTC (4-5 PM ET, after market close)
   and posts straight to Discord. Change the `cron` line in the workflow
   file if you want a different time.
4. To test it immediately instead of waiting: go to the **Actions** tab →
   **Daily Stock Coach** → **Run workflow**.

`positions.json` gets committed back to the repo automatically after each
run, so HOLD/SELL tracking persists between runs.

## Automating the daily run (Windows Task Scheduler — local alternative)

Windows Task Scheduler, daily after market close:
```powershell
schtasks /create /tn "CP Daily Coach" /tr "python C:\path\to\scan.py" /sc daily /st 16:30
```

## Files

```
config.py          - all tunable settings (weights, thresholds, universe)
universe.py         - fetches + caches the S&P 500 ticker list
indicators.py        - EMA/SMA/RSI/ATR/volume calculations
scorer.py             - confidence scoring + BUY/SELL/HOLD/DO NOTHING logic
positions.py           - tracks what you're actually holding
discord_alert.py        - formats and sends the daily message
scan.py                  - main entry point, run this daily (after close)
premarket.py              - pre-market movers scan, run before open
midday.py                  - midday movers check-in
test_synthetic.py         - sanity check with fake data, no network needed
```

## Disclaimer

Educational tool, not financial advice. The scoring logic is unvalidated —
consider backtesting the entry criteria (same approach as
`cp-rules-backtest`) before trusting the BUY signals with real money.
