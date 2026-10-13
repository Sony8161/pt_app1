"""Calendar helpers. Everything is UTC (see .claude/rules/core/TIMEZONE.md)."""

from __future__ import annotations

import datetime as dt

# Each employee gives one project their full working day.
DAILY_HOURS = 8
WORK_WEEK_HOURS = 40


def today() -> dt.date:
    """Today's date in UTC. Services call this (never ``date.today()``) so tests can freeze it."""
    return dt.datetime.now(dt.UTC).date()


def now() -> dt.datetime:
    """Current UTC timestamp."""
    return dt.datetime.now(dt.UTC)


def week_start(day: dt.date) -> dt.date:
    """Monday of the week containing ``day``."""
    return day - dt.timedelta(days=day.weekday())
