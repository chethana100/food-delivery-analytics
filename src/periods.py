"""Calendar period helpers. Weeks are Monday-Sunday, in the reporting timezone."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import REPORTING_TZ

PERIOD_CHOICES = ["Current week", "Current month", "Current year", "Custom range"]


def today_local() -> date:
    return datetime.now(ZoneInfo(REPORTING_TZ)).date()


def week_range(d: date) -> tuple[date, date]:
    """Monday..Sunday containing d (may span a month/year boundary)."""
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def month_range(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, nxt - timedelta(days=1)


def year_range(d: date) -> tuple[date, date]:
    return date(d.year, 1, 1), date(d.year, 12, 31)


def resolve_period(choice: str, as_of: date, custom: tuple[date, date] | None = None):
    """Return (start, end) inclusive for a named period."""
    if choice == "Current week":
        return week_range(as_of)
    if choice == "Current month":
        return month_range(as_of)
    if choice == "Current year":
        return year_range(as_of)
    if choice == "Custom range":
        if not custom:
            raise ValueError("custom range requires (start, end)")
        s, e = custom
        return (s, e) if s <= e else (e, s)
    raise ValueError(f"unknown period: {choice}")


def format_range(start: date, end: date) -> str:
    return f"{start:%d %b %Y} – {end:%d %b %Y}"
