from __future__ import annotations

from collections.abc import Iterable, Mapping
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


def due_source_ids(
    *,
    source_rows: Iterable[Mapping[str, object]],
    local_date: date,
    allowed_roles: Iterable[str] | None = None,
    required_priority: str | None = None,
) -> set[str]:
    """Return SourceRegistry IDs that must receive a source-level route today.

    This helper deliberately derives requirements from registry state rather
    than from a second hard-coded source list. Callers may scope enforcement to
    selected source roles and/or a priority class, but cadence remains owned by
    each SourceRegistry row.

    Rows with an unsupported scheduling rule fail closed through
    :func:`source_required_today`. A due row without ``source_id`` is also an
    error because it cannot be reconciled to a persisted route.
    """
    roles = None
    if allowed_roles is not None:
        roles = {str(value).strip() for value in allowed_roles if str(value).strip()}
    priority = str(required_priority or "").strip()

    due: set[str] = set()
    for row in source_rows:
        status = str(row.get("status", "")).strip()
        if status.lower() != "active":
            continue
        if roles is not None and str(row.get("source_role", "")).strip() not in roles:
            continue
        if priority and str(row.get("priority", "")).strip() != priority:
            continue
        if not source_required_today(
            local_date=local_date,
            required_today_rule=str(row.get("required_today_rule", "")),
            rotation_group=str(row.get("rotation_group", "")),
            status=status,
        ):
            continue
        source_id = str(row.get("source_id", "")).strip()
        if not source_id:
            raise ValueError("due SourceRegistry row is missing source_id")
        due.add(source_id)
    return due


def due_source_route_ids(
    *,
    source_rows: Iterable[Mapping[str, object]],
    local_date: date,
    allowed_roles: Iterable[str] | None = None,
    required_priority: str | None = None,
) -> set[str]:
    """Return canonical Worker source-route IDs for due registry sources."""
    return {
        f"worker/source/{source_id}"
        for source_id in due_source_ids(
            source_rows=source_rows,
            local_date=local_date,
            allowed_roles=allowed_roles,
            required_priority=required_priority,
        )
    }
