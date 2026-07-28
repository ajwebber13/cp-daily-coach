"""
positions.py
Tracks trades you've actually entered, so the coach knows to show HOLD/SELL
instead of BUY for tickers you're already in. This is manual — you tell it
when you enter a trade. It does not place trades for you.

CLI usage:
    python positions.py add NVDA 192.35
    python positions.py remove NVDA
    python positions.py list
"""
import json
import os
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python positions.py [add TICKER PRICE | remove TICKER | list]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) >= 4:
        add_position(sys.argv[2], float(sys.argv[3]))
    elif cmd == "remove" and len(sys.argv) >= 3:
        remove_position(sys.argv[2])
    elif cmd == "list":
        for ticker, info in list_positions().items():
            print(f"{ticker}: {info}")
    else:
        print("Usage: python positions.py [add TICKER PRICE | remove TICKER | list]")
