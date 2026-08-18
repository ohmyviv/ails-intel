from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation

WORKER_PRODUCERS = {"chatgpt/worker", "chatgpt/rescue"}
AUDIT_ROW_TYPES = {"route_summary", "result"}
AUDIT_DISPOSITIONS = {"qualified_signal", "rejected"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _nonnegative_int(value: object) -> int | None:
    """Parse a Sheet scalar as an exact non-negative integer.

    Audit count fields are execution facts. Placeholder text such as
    ``UNRESOLVED_ATTRIBUTION`` must never be silently coerced to zero.
    """
    text = _text(value)
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        return None
    return int(number)


def _route_key(row: Mapping[str, object]) -> tuple[str, str]:
    return (_text(row.get("channel_id")), _text(row.get("route_id")))


def validate_worker_audit_snapshot(
    *,
    run_key: str,
    attempt_id: str,
    audit_rows: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
    active_signals: Iterable[Mapping[str, object]],
    required_routes: Mapping[str, set[str]],
    max_result_rows_per_route: int = 5,
) -> list[str]:
    """Validate the G3 Worker Audit -> Signal -> Coverage transaction.

    The validator is deliberately route-scoped and fail-closed. In particular,
    ``results_returned`` and the other route-summary count fields must be
    numeric execution facts. An attribution-degraded multi-query execution may
    be persisted as partial/failed evidence, but an unresolved placeholder is
    not a valid count and cannot pass G3 before Candidate formation.
    """
    expected_routes = {
        (str(channel).strip(), str(route_id).strip())
        for channel, routes in required_routes.items()
        for route_id in routes
        if str(channel).strip() and str(route_id).strip()
    }
    max_rows = max(0, int(max_result_rows_per_route))
    errors: list[str] = []

    audit = [
        row
        for row in audit_rows
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
    ]
    coverage = [
        row
        for row in coverage_rows
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
    ]
    signals = [
        row
        for row in active_signals
        if _text(row.get("run_key")) == run_key
        and _text(row.get("origin_attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
        and _text(row.get("signal_state")) == "active"
    ]

    audit_ids: set[str] = set()
    for row in audit:
        audit_id = _text(row.get("audit_id"))
        if not audit_id:
            errors.append("worker_audit_id_missing")
        elif audit_id in audit_ids:
            errors.append("worker_audit_id_duplicate")
        else:
            audit_ids.add(audit_id)
        if _text(row.get("row_type")) not in AUDIT_ROW_TYPES:
            errors.append("worker_audit_row_type_invalid")

    summaries_by_route: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    results_by_route: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in audit:
        key = _route_key(row)
        if _text(row.get("row_type")) == "route_summary":
            summaries_by_route.setdefault(key, []).append(row)
        elif _text(row.get("row_type")) == "result":
            results_by_route.setdefault(key, []).append(row)

    coverage_by_route: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in coverage:
        coverage_by_route.setdefault(_route_key(row), []).append(row)

    signals_by_route: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in signals:
        signals_by_route.setdefault(_route_key(row), []).append(row)

    count_fields = (
        "results_returned",
        "results_screened",
        "pages_opened",
        "fresh_results",
        "qualifying_results",
    )

    for channel, route_id in sorted(expected_routes):
        key = (channel, route_id)
        summaries = summaries_by_route.get(key, [])
        if not summaries:
            errors.append(f"worker_audit_route_summary_missing:{channel}")
            continue
        if len(summaries) != 1:
            errors.append(f"worker_audit_route_summary_duplicate:{channel}")
            continue

        summary = summaries[0]
        parsed: dict[str, int] = {}
        for field in count_fields:
            value = _nonnegative_int(summary.get(field))
            if value is None:
                errors.append(f"worker_audit_noninteger:{field}")
            else:
                parsed[field] = value
        if len(parsed) != len(count_fields):
            # Further reconciliation would require inventing a missing count.
            continue

        returned = parsed["results_returned"]
        screened = parsed["results_screened"]
        pages_opened = parsed["pages_opened"]
        fresh = parsed["fresh_results"]
        qualifying = parsed["qualifying_results"]

        if screened > returned:
            errors.append("worker_audit_screened_exceeds_returned")
        if fresh > screened:
            errors.append("worker_audit_fresh_exceeds_screened")
        if qualifying > screened:
            errors.append("worker_audit_qualifying_exceeds_screened")

        result_rows = results_by_route.get(key, [])
        expected_result_rows = min(screened, max_rows)
        if len(result_rows) != expected_result_rows:
            errors.append(f"worker_audit_result_row_count_mismatch:{channel}")

        execution_status = _text(summary.get("execution_status"))
        if execution_status == "complete" and returned == 0:
            if any((screened, pages_opened, fresh, qualifying)) or result_rows:
                errors.append("worker_audit_true_zero_inconsistent")

        qualified_result_signal_ids: set[str] = set()
        for result in result_rows:
            disposition = _text(result.get("disposition"))
            if disposition not in AUDIT_DISPOSITIONS:
                errors.append("worker_audit_result_disposition_invalid")
                continue
            if disposition == "rejected":
                if not _text(result.get("reject_reason")):
                    errors.append("worker_audit_reject_reason_missing")
            else:
                signal_id = _text(result.get("signal_id"))
                if not signal_id:
                    errors.append("worker_audit_qualified_signal_id_missing")
                else:
                    qualified_result_signal_ids.add(signal_id)

        matching_coverage = coverage_by_route.get(key, [])
        if not matching_coverage:
            errors.append(f"worker_audit_coverage_missing:{channel}")
        elif len(matching_coverage) != 1:
            errors.append(f"worker_audit_coverage_duplicate:{channel}")
        else:
            coverage_row = matching_coverage[0]
            results_seen = _nonnegative_int(coverage_row.get("results_seen"))
            relevant_count = _nonnegative_int(coverage_row.get("relevant_signal_count"))
            if results_seen is None:
                errors.append("worker_audit_coverage_results_seen_noninteger")
            elif results_seen != screened:
                errors.append("worker_audit_results_seen_mismatch")
            if relevant_count is None:
                errors.append("worker_audit_coverage_relevant_count_noninteger")
            elif relevant_count != qualifying:
                errors.append("worker_audit_coverage_qualifying_mismatch")

        route_signals = signals_by_route.get(key, [])
        route_signal_ids = {_text(row.get("signal_id")) for row in route_signals if _text(row.get("signal_id"))}
        if len(route_signal_ids) != qualifying:
            errors.append("worker_audit_qualifying_signal_count_mismatch")
        if not qualified_result_signal_ids.issubset(route_signal_ids):
            errors.append("worker_audit_result_signal_unresolved")

    # Orphan same-attempt Worker rows are also an integrity defect: they cannot
    # be silently ignored by a required-route reconciliation.
    for key in summaries_by_route:
        if key not in expected_routes:
            errors.append("worker_audit_orphan_route_summary")
    for key in coverage_by_route:
        if key not in expected_routes:
            errors.append("worker_audit_orphan_coverage_route")

    return sorted(set(errors))
