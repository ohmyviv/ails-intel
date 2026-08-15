from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


DATE_MOD_3_GROUP_REMAINDERS = {"A": 0, "B": 1, "C": 2}


def local_calendar_date(when: datetime, timezone_name: str) -> date:
    """Return the calendar date used for source scheduling.

    Source cadence is evaluated in the configured reporting timezone, not UTC.
    Naive datetimes are rejected so callers cannot silently schedule against an
    ambiguous timezone.
    """
    if when.tzinfo is None:
        raise ValueError("source schedule datetime must be timezone-aware")
    return when.astimezone(ZoneInfo(timezone_name)).date()


def date_mod_3_bucket(local_date: date) -> int:
    """Return the stable three-day rotation bucket for a local calendar date.

    ``date.toordinal()`` is continuous across month and year boundaries, unlike
    day-of-month arithmetic. The resulting schedule therefore never resets on
    the first of a month.
    """
    return local_date.toordinal() % 3


def rotation_group_due(local_date: date, rotation_group: str) -> bool:
    group = str(rotation_group or "").strip().upper()
    if group not in DATE_MOD_3_GROUP_REMAINDERS:
        raise ValueError(f"unsupported rotation_group: {rotation_group!r}")
    return date_mod_3_bucket(local_date) == DATE_MOD_3_GROUP_REMAINDERS[group]


def source_required_today(
    *,
    local_date: date,
    required_today_rule: str,
    rotation_group: str = "",
    status: str = "active",
) -> bool:
    """Evaluate the deterministic SourceRegistry ``required_today_rule``.

    Supported rules are intentionally explicit. Unknown rules fail closed via
    ``ValueError`` rather than being guessed by a worker.
    """
    if str(status or "").strip().lower() != "active":
        return False

    rule = str(required_today_rule or "").strip().lower()
    if rule == "all_active_daily":
        return True
    if rule == "date_mod_3":
        return rotation_group_due(local_date, rotation_group)
    if not rule:
        return False
    raise ValueError(f"unsupported required_today_rule: {required_today_rule!r}")
