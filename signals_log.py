"""
signals_log.py
Appends every BUY/PUT WATCH signal actually shown to Discord to
SIGNALS_LOG_FILE (config.py), one JSON object per line. This is the only
place a signal gets recorded for later grading — see grade_signals.py,
which reads this file to check whether each one hit its target, hit its
stop, or went nowhere.

Deliberately dumb: appends only, never reads its own file back, never
mutates a past line. Grading state lives in a separate file
(signals_outcomes.jsonl) so this log can't be corrupted by a bad grading
run.
"""
import json
from datetime import date

import config

FIELDS = ("ticker", "signal", "score", "entry", "stop", "target")


def _to_record(result: dict, today: str) -> dict:
    record = {"date": today}
    for field in FIELDS:
        record[field] = result.get(field)
    record["reward_risk"] = result.get("reward_risk_ratio")
    return record


def log_signals(buy_signals: list, put_signals: list, log_file: str = None) -> int:
    """
    Appends one record per BUY/PUT WATCH result to log_file (default
    config.SIGNALS_LOG_FILE). Returns the number of records written.
    """
    log_file = log_file or config.SIGNALS_LOG_FILE
    today = str(date.today())
    records = [_to_record(r, today) for r in buy_signals + put_signals]

    if not records:
        return 0

    with open(log_file, "a") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    return len(records)
