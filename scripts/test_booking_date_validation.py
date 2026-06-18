"""Unit tests for Bug 3 — past-date booking validation.

Run: python scripts/test_booking_date_validation.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.booking_agent import BookingAgent  # noqa: E402

agent = BookingAgent()
TODAY = date(2026, 6, 18)

CASES: list[tuple[str, bool]] = [
    # (date string, expected is_past_date)
    ("17 June 2026", True),       # yesterday
    ("18 June 2026", False),      # today
    ("19 June 2026", False),      # tomorrow
    ("15 July 2026", False),      # future
    ("2026-06-17", True),         # ISO past
    ("2026-06-18", False),        # ISO today
    ("2026-12-31", False),        # ISO future
    ("17/06/2026", True),         # DD/MM/YYYY past
    ("19/06/2026", False),        # DD/MM/YYYY future
    ("01 January 2020", True),    # far past
    ("", False),                  # empty -> not past
    (None, False),                # none -> not past
    ("sometime soon", False),     # unparseable -> not past
]


def main() -> int:
    failures = 0
    for value, expected in CASES:
        result = agent.is_past_date(value, today=TODAY)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"[{status}] is_past_date({value!r}) -> {result} (expected {expected})")

    # Parsing sanity checks
    assert agent.parse_date("15 July 2026") == date(2026, 7, 15)
    assert agent.parse_date("2026-07-15") == date(2026, 7, 15)
    assert agent.parse_date("15/07/2026") == date(2026, 7, 15)
    assert agent.parse_date("garbage") is None

    print("\nTODAY (reference):", TODAY, "| real today:", date.today())
    print(f"RESULT: {len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
