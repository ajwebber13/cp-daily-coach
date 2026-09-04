"""
test_grade_signals.py
Sanity check for grade_signals.py's resolve_outcome() and summarize()
using hand-built price paths — no network needed. Confirms target/stop
resolution order, the same-day-ambiguity tiebreak, expiry, and the "open"
state all work for both BUY and PUT WATCH signals.
"""
import pandas as pd

from grade_signals import resolve_outcome, summarize


def bars(rows: list) -> pd.DataFrame:
    """rows: list of (high, low) tuples, oldest first (row 1 = day after entry)."""
    return pd.DataFrame(
        [{"high": h, "low": l} for h, l in rows],
        index=pd.bdate_range("2026-01-05", periods=len(rows)),
    )


def test_buy_hits_target_before_stop():
    signal = {"signal": "BUY", "entry": 100, "stop": 90, "target": 115}
    price_df = bars([(102, 98), (108, 101), (117, 110)])  # target cleared on day 3
    outcome, days = resolve_outcome(signal, price_df)
    assert outcome == "hit_target"
    assert days == 3


def test_buy_hits_stop_before_target():
    signal = {"signal": "BUY", "entry": 100, "stop": 90, "target": 115}
    price_df = bars([(101, 95), (99, 88), (105, 100)])  # stop broken on day 2
    outcome, days = resolve_outcome(signal, price_df)
    assert outcome == "hit_stop"
    assert days == 2


def test_buy_same_day_ambiguity_resolves_to_stop():
    signal = {"signal": "BUY", "entry": 100, "stop": 90, "target": 115}
    price_df = bars([(118, 85)])  # both target and stop touched on day 1
    outcome, days = resolve_outcome(signal, price_df)
    assert outcome == "hit_stop"
    assert days == 1


def test_buy_expires_flat_after_max_days():
    signal = {"signal": "BUY", "entry": 100, "stop": 90, "target": 115}
    price_df = bars([(105, 95)] * 25)  # never leaves the range, well past max_days
    outcome, days = resolve_outcome(signal, price_df, max_days=20)
    assert outcome == "expired_flat"
    assert days == 20


def test_buy_still_open_with_too_few_days():
    signal = {"signal": "BUY", "entry": 100, "stop": 90, "target": 115}
    price_df = bars([(105, 95)] * 6)  # only 6 rows, under max_days=20
    outcome, days = resolve_outcome(signal, price_df, max_days=20)
    assert outcome == "open"
    assert days is None


def test_put_watch_hits_target_before_stop():
    signal = {"signal": "PUT WATCH", "entry": 100, "stop": 110, "target": 85}
    price_df = bars([(103, 96), (99, 90), (95, 84)])  # target (low <= 85) cleared day 3
    outcome, days = resolve_outcome(signal, price_df)
    assert outcome == "hit_target"
    assert days == 3


def test_put_watch_hits_stop_before_target():
    signal = {"signal": "PUT WATCH", "entry": 100, "stop": 110, "target": 85}
    price_df = bars([(105, 97), (112, 104)])  # stop (high >= 110) broken day 2
    outcome, days = resolve_outcome(signal, price_df)
    assert outcome == "hit_stop"
    assert days == 2


def test_summarize_hit_rate_and_avg_r():
    outcomes = [
        {"signal": "BUY", "outcome": "hit_target", "reward_risk": 1.5},
        {"signal": "BUY", "outcome": "hit_stop", "reward_risk": 1.5},
        {"signal": "BUY", "outcome": "expired_flat", "reward_risk": 1.6},
        {"signal": "BUY", "outcome": "open", "reward_risk": 1.5},
    ]
    summary = summarize(outcomes)
    assert summary["count"] == 3          # open excluded from resolved count
    assert summary["open_count"] == 1
    assert summary["hit_rate"] == round(1 / 3 * 100, 1)
    expected_avg_r = round((1.5 + -1.0 + 0.0) / 3, 2)
    assert summary["avg_r"] == expected_avg_r


def test_summarize_empty_returns_none():
    assert summarize([]) is None
    assert summarize([{"signal": "BUY", "outcome": "open", "reward_risk": 1.5}]) is None


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\nAll {len(tests)} grade_signals sanity checks passed.")


if __name__ == "__main__":
    main()
