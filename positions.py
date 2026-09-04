"""
positions.py
Tracks trades you've actually entered, so the coach knows to show HOLD/SELL
instead of BUY for tickers you're already in. This is manual — you tell it
when you enter a trade. It does not place trades for you.

The cloud-scheduled daily scan starts from a fresh checkout every run, so
it only ever sees what's actually committed to the repo. Running `add` or
`remove` from the command line auto-commits and pushes positions.json
right after saving it, so the next scan (wherever it runs) sees it —
without this, a position added locally would silently never reach the
cloud scan. (Positions changed automatically mid-scan, e.g. a SELL
removing a closed position, are NOT synced here — daily-scan.yml already
commits positions.json itself at the end of that run.)

CLI usage:
    python positions.py add NVDA 192.35
    python positions.py remove NVDA
    python positions.py list
"""
import json
import os
import subprocess
import sys
from datetime import date

import config


def _load() -> dict:
    if not os.path.exists(config.POSITIONS_FILE):
        return {}
    with open(config.POSITIONS_FILE) as f:
        return json.load(f)


def _save(positions: dict):
    with open(config.POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


def add_position(ticker: str, entry_price: float, stop_price: float = None):
    positions = _load()
    positions[ticker.upper()] = {
        "entry_price": entry_price,
        "entry_date": str(date.today()),
        "highest_close": entry_price,
        "stop": stop_price if stop_price is not None else entry_price * 0.95,
    }
    _save(positions)
    print(f"Added {ticker.upper()} @ {entry_price}")


def remove_position(ticker: str):
    positions = _load()
    if ticker.upper() in positions:
        del positions[ticker.upper()]
        _save(positions)
        print(f"Removed {ticker.upper()}")
    else:
        print(f"{ticker.upper()} not found in positions.")


def update_highest_close(ticker: str, close_price: float):
    """Called by scan.py each run to track the highest close for trailing stops."""
    positions = _load()
    if ticker in positions:
        positions[ticker]["highest_close"] = max(positions[ticker]["highest_close"], close_price)
        _save(positions)


def list_positions() -> dict:
    return _load()


def _sync_to_git(commit_message: str):
    """
    Best-effort commit + push of positions.json so the cloud scan sees
    this change on its next run. Never raises — a sync failure shouldn't
    stop you from recording a trade locally, it just means you'll need to
    push manually.
    """
    try:
        subprocess.run(["git", "add", config.POSITIONS_FILE], check=True, capture_output=True, text=True)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", config.POSITIONS_FILE], capture_output=True
        )
        if staged.returncode == 0:
            return  # nothing actually changed (e.g. re-adding the same position)

        subprocess.run(["git", "commit", "-m", commit_message], check=True, capture_output=True, text=True)
        subprocess.run(["git", "push"], check=True, capture_output=True, text=True)
        print("Synced positions.json to git (committed + pushed).")
    except FileNotFoundError:
        print("git not found on PATH — positions.json was saved locally but not synced. "
              "Push it manually so the cloud scan sees this.")
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or str(e)).strip()
        print(f"positions.json saved locally, but git sync failed: {detail}\n"
              f"Push it manually so the cloud scan sees this.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python positions.py [add TICKER PRICE | remove TICKER | list]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) >= 4:
        ticker = sys.argv[2]
        add_position(ticker, float(sys.argv[3]))
        _sync_to_git(f"Add {ticker.upper()} to positions.json [manual]")
    elif cmd == "remove" and len(sys.argv) >= 3:
        ticker = sys.argv[2]
        remove_position(ticker)
        _sync_to_git(f"Remove {ticker.upper()} from positions.json [manual]")
    elif cmd == "list":
        for ticker, info in list_positions().items():
            print(f"{ticker}: {info}")
    else:
        print("Usage: python positions.py [add TICKER PRICE | remove TICKER | list]")
