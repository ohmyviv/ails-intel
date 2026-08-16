from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, time

from ails_intel.structured_signal_identity import validate_structured_coverage_signal_identity


TERMINAL_COLLECTOR_STATUSES = {"complete", "partial", "failed", "skipped"}


def enabled_structured_collector_ids(cfg: Mapping[str, object]) -> set[str]:
    """Return all enabled structured collector IDs from private runtime config.

    Snapshot integrity is about observing every enabled collector in the current
    run, not about requiring every source to retrieve successfully. Private
    locators and query text never enter this public contract.
    """
    out: set[str] = set()
    raw = cfg.get("structured_collectors_json", []) or []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        collector_id = str(item.get("id", "")).strip()
        enabled = item.get("enabled", True)
        if collector_id and enabled not in {False, "FALSE", "false", 0, "0"}:
            out.add(collector_id)
    return out


def barrier_required_structured_collector_ids(cfg: Mapping[str, object]) -> set[str]:
    """Compatibility alias for the Snapshot Barrier observation set.

    Legacy ``barrier_required`` flags no longer grant an individual source a
    transaction veto. Every enabled collector must instead leave one fresh,
    terminal diagnostic row. Retrieval success/failure is classified later as
    coverage quality.
    """
    return enabled_structured_collector_ids(cfg)


def _parse_clock(value: object) -> time:
    text = str(value or "18:00:00").strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError("invalid snapshot barrier clock")


def validate_structured_snapshot_barrier(
    *,
    run_key: str,
    report_date: str,
    coverage_rows: Iterable[Mapping[str, object]],
    expected_collector_ids: Iterable[str],
    not_before_bjt: object = "18:00:00",
    current_active_signal_count: int | None = None,
    declared_signal_count: object | None = None,
    active_signal_rows: Iterable[Mapping[str, object]] | None = None,
) -> list[str]:
    """Validate fresh terminal observation and structured Signal identity.

    ``complete``, ``partial``, ``failed`` and ``skipped`` are all terminal
    observations. A failed/skipped source therefore degrades coverage but does
    not fail Snapshot Barrier by itself. Missing, duplicate, stale, malformed,
    non-terminal, or per-route persisted Signal identity mismatches remain
    fail-closed integrity errors.
    """
    errors: list[str] = []
    expected = {str(x).strip() for x in expected_collector_ids if str(x).strip()}
    try:
        minimum_clock = _parse_clock(not_before_bjt)
    except ValueError:
        return ["structured_snapshot_invalid_barrier_clock"]

    structured_rows = [
        row
        for row in coverage_rows
        if str(row.get("run_key", "")).strip() == run_key
        and str(row.get("producer_id", "")).strip().startswith("collector/")
    ]
    by_collector: dict[str, list[Mapping[str, object]]] = {}
    for row in structured_rows:
        producer = str(row.get("producer_id", "")).strip()
        collector_id = producer.removeprefix("collector/")
        if collector_id:
            by_collector.setdefault(collector_id, []).append(row)

    for collector_id in sorted(expected):
        matches = by_collector.get(collector_id, [])
        if not matches:
            errors.append("structured_snapshot_missing_collector")
            continue
        if len(matches) != 1:
            errors.append("structured_snapshot_duplicate_collector")
            continue

        row = matches[0]
        status = str(row.get("execution_status", "")).strip()
        if status not in TERMINAL_COLLECTOR_STATUSES:
            errors.append("structured_snapshot_nonterminal_collector")

        checked_raw = str(row.get("checked_at_bjt", "")).strip()
        try:
            checked = datetime.fromisoformat(checked_raw)
        except ValueError:
            errors.append("structured_snapshot_invalid_checked_at")
            continue
        if checked.date().isoformat() != report_date or checked.time().replace(tzinfo=None) < minimum_clock:
            errors.append("structured_snapshot_stale_collector")

    if active_signal_rows is not None:
        errors.extend(
            validate_structured_coverage_signal_identity(
                run_key=run_key,
                coverage_rows=structured_rows,
                active_signals=active_signal_rows,
            )
        )

    if current_active_signal_count is not None and declared_signal_count is not None:
        try:
            declared = int(float(str(declared_signal_count or "0")))
        except ValueError:
            errors.append("structured_snapshot_invalid_declared_signal_count")
        else:
            if declared != int(current_active_signal_count):
                errors.append("signal_count_snapshot_drift")

    return sorted(set(errors))
