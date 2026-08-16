from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


WORKER_PRODUCERS = {"chatgpt/worker", "chatgpt/rescue"}


@dataclass(frozen=True)
class DueSourceReconciliation:
    errors: tuple[str, ...]
    required_route_count: int
    completed_route_count: int
    incomplete_route_count: int


def _text(value: object) -> str:
    return str(value or "").strip()


def reconcile_due_source_routes(
    *,
    run_key: str,
    attempt_id: str,
    due_source_route_ids: Iterable[str],
    audit_rows: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
) -> DueSourceReconciliation:
    """Reconcile registry-derived due source routes against persisted evidence.

    Missing or duplicate persistence is an integrity error. A route that exists
    but is ``partial``/``failed``/``skipped`` is counted as incomplete coverage,
    not as a transaction-integrity error. Error labels are intentionally compact
    so public CI logs do not disclose private source identities.
    """
    required = {str(route).strip() for route in due_source_route_ids if str(route).strip()}
    audits = [
        row
        for row in audit_rows
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
        and _text(row.get("row_type")) == "route_summary"
    ]
    coverage = [
        row
        for row in coverage_rows
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
    ]

    errors: list[str] = []
    completed = 0
    incomplete = 0
    for route_id in sorted(required):
        route_audits = [row for row in audits if _text(row.get("route_id")) == route_id]
        route_coverage = [row for row in coverage if _text(row.get("route_id")) == route_id]

        if len(route_audits) != 1:
            errors.append(
                "due_source_audit_missing" if not route_audits else "due_source_audit_duplicate"
            )
        if len(route_coverage) != 1:
            errors.append(
                "due_source_coverage_missing" if not route_coverage else "due_source_coverage_duplicate"
            )
        if len(route_audits) != 1 or len(route_coverage) != 1:
            continue

        audit = route_audits[0]
        cov = route_coverage[0]
        expected_source_id = route_id.removeprefix("worker/source/")
        if not route_id.startswith("worker/source/") or not expected_source_id:
            errors.append("due_source_route_id_invalid")
        if _text(audit.get("source_id")) != expected_source_id:
            errors.append("due_source_audit_source_mismatch")
        if _text(cov.get("source_id")) != expected_source_id:
            errors.append("due_source_coverage_source_mismatch")
        if _text(audit.get("channel_id")) != _text(cov.get("channel_id")):
            errors.append("due_source_channel_mismatch")

        audit_status = _text(audit.get("execution_status"))
        coverage_status = _text(cov.get("execution_status"))
        if audit_status != coverage_status:
            errors.append("due_source_execution_status_mismatch")
        if audit_status == "complete" and coverage_status == "complete":
            completed += 1
        else:
            incomplete += 1

    return DueSourceReconciliation(
        errors=tuple(sorted(set(errors))),
        required_route_count=len(required),
        completed_route_count=completed,
        incomplete_route_count=incomplete,
    )
