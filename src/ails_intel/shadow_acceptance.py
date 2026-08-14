from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

from ails_intel.fingerprint import frozen_manifest_fingerprint
from ails_intel.snapshot_policy import (
    barrier_required_structured_collector_ids,
    validate_structured_snapshot_barrier,
)
from ails_intel.unified_ingestion import WORKER_PRODUCERS, validate_unified_ingestion_snapshot

CONTINUATION_POLICY_EFFECTIVE_DATE = date(2026, 8, 15)
VALID_COVERAGE = {"HIGH", "MEDIUM", "LOW"}


@dataclass(frozen=True)
class AcceptanceResult:
    ledger_verdict: str
    source_failure_path: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: Mapping[str, object]


def _text(value: object) -> str:
    return str(value or "").strip()


def _boolish(value: object) -> bool:
    return _text(value).lower() in {"true", "1", "yes"}


def _int(value: object, default: int = -1) -> int:
    try:
        return int(float(_text(value)))
    except (TypeError, ValueError):
        return default


def _channel_health(run: Mapping[str, object]) -> dict[str, str]:
    raw = _text(run.get("channel_health_json"))
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): _text(value) for key, value in parsed.items()}


def _worker_audit_errors(
    *,
    run_key: str,
    attempt_id: str,
    required_routes: Mapping[str, set[str]],
    active_signals: list[Mapping[str, object]],
    coverage_rows: list[Mapping[str, object]],
    audit_rows: list[Mapping[str, object]],
    max_result_rows: int,
) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    rows = [
        row
        for row in audit_rows
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
    ]
    audit_ids = [_text(row.get("audit_id")) for row in rows if _text(row.get("audit_id"))]
    if len(audit_ids) != len(set(audit_ids)):
        errors.append("worker_audit_id_not_unique")

    summaries: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    results: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in rows:
        key = (_text(row.get("channel_id")), _text(row.get("route_id")))
        if _text(row.get("row_type")) == "route_summary":
            summaries.setdefault(key, []).append(row)
        elif _text(row.get("row_type")) == "result":
            results.setdefault(key, []).append(row)

    worker_coverage: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in coverage_rows:
        if _text(row.get("run_key")) != run_key or _text(row.get("attempt_id")) != attempt_id:
            continue
        if _text(row.get("producer_id")) not in WORKER_PRODUCERS:
            continue
        worker_coverage.setdefault((_text(row.get("channel_id")), _text(row.get("route_id"))), []).append(row)

    worker_signals: dict[tuple[str, str], int] = {}
    active_signal_ids = set()
    for row in active_signals:
        sid = _text(row.get("signal_id"))
        if sid:
            active_signal_ids.add(sid)
        if _text(row.get("origin_attempt_id")) != attempt_id:
            continue
        if _text(row.get("producer_id")) not in WORKER_PRODUCERS:
            continue
        key = (_text(row.get("channel_id")), _text(row.get("route_id")))
        worker_signals[key] = worker_signals.get(key, 0) + 1

    required_count = 0
    summary_count = 0
    representative_count = 0
    for channel, routes in required_routes.items():
        for route in routes:
            required_count += 1
            key = (channel, route)
            route_summaries = summaries.get(key, [])
            if len(route_summaries) != 1:
                errors.append(f"worker_audit_route_summary_count:{channel}")
                continue
            summary_count += 1
            summary = route_summaries[0]
            screened = _int(summary.get("results_screened"))
            qualifying = _int(summary.get("qualifying_results"))
            if screened < 0 or qualifying < 0:
                errors.append(f"worker_audit_invalid_counts:{channel}")
                continue

            route_results = results.get(key, [])
            representative_count += len(route_results)
            expected_result_rows = min(screened, max(0, max_result_rows))
            if len(route_results) != expected_result_rows:
                errors.append(f"worker_audit_representative_count:{channel}")

            coverage_matches = worker_coverage.get(key, [])
            if not coverage_matches:
                errors.append(f"worker_audit_without_coverage:{channel}")
            elif not any(_int(row.get("results_seen")) == screened for row in coverage_matches):
                errors.append(f"worker_audit_results_seen_mismatch:{channel}")

            if worker_signals.get(key, 0) != qualifying:
                errors.append(f"worker_audit_signal_reconciliation:{channel}")

            for result in route_results:
                disposition = _text(result.get("disposition"))
                if disposition == "qualified_signal":
                    sid = _text(result.get("signal_id"))
                    if not sid or sid not in active_signal_ids:
                        errors.append(f"worker_audit_result_signal_missing:{channel}")
                elif disposition == "rejected":
                    if not _text(result.get("reject_reason")):
                        errors.append(f"worker_audit_reject_reason_missing:{channel}")
                else:
                    errors.append(f"worker_audit_invalid_disposition:{channel}")

    return sorted(set(errors)), {
        "required_worker_route_count": required_count,
        "worker_audit_summary_count": summary_count,
        "worker_audit_representative_count": representative_count,
    }


def _manifest_errors(
    *,
    run_key: str,
    attempt_id: str,
    run: Mapping[str, object],
    candidates: list[Mapping[str, object]],
    daily_items: list[Mapping[str, object]],
    event_index_rows: list[Mapping[str, object]],
    max_items: int,
) -> list[str]:
    errors: list[str] = []
    items = [
        row
        for row in daily_items
        if _text(row.get("run_key")) == run_key and _text(row.get("attempt_id")) == attempt_id
    ]
    selected = {
        _text(row.get("delta_key")): row
        for row in candidates
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("disposition")) == "selected"
        and _text(row.get("delta_key"))
    }
    if not items:
        errors.append("no_frozen_items")
    if len(items) > max(0, max_items):
        errors.append("frozen_item_count_exceeds_max")

    indices: list[int] = []
    event_keys: set[str] = set()
    delta_keys: set[str] = set()
    for item in items:
        idx = _int(item.get("item_index"))
        if idx < 1:
            errors.append("dailyitem_invalid_item_index")
        else:
            indices.append(idx)
        title = _text(item.get("title"))
        primary_url = _text(item.get("primary_url"))
        event_key = _text(item.get("event_key_v11"))
        delta_key = _text(item.get("delta_key"))
        if not title:
            errors.append("dailyitem_missing_title")
        if not primary_url:
            errors.append("dailyitem_missing_primary_url")
        if not event_key or event_key in event_keys:
            errors.append("dailyitem_event_key_invalid_or_duplicate")
        if not delta_key or delta_key in delta_keys:
            errors.append("dailyitem_delta_key_invalid_or_duplicate")
        event_keys.add(event_key)
        delta_keys.add(delta_key)
        candidate = selected.get(delta_key)
        if candidate is None:
            errors.append("dailyitem_not_from_selected_candidate")
        elif _text(candidate.get("event_key_v11")) != event_key:
            errors.append("dailyitem_candidate_event_key_mismatch")

    if sorted(indices) != list(range(1, len(items) + 1)):
        errors.append("dailyitem_indices_not_contiguous")
    if len(selected) != len(items):
        errors.append("selected_candidate_count_mismatch")
    if _int(run.get("frozen_item_count")) != len(items):
        errors.append("frozen_item_count_mismatch")
    if _int(run.get("selected_count")) != len(items):
        errors.append("selected_count_mismatch")

    if items:
        try:
            expected_fingerprint = frozen_manifest_fingerprint([dict(row) for row in items])
        except (KeyError, TypeError, ValueError):
            errors.append("frozen_fingerprint_input_invalid")
        else:
            if _text(run.get("frozen_content_fingerprint")) != expected_fingerprint:
                errors.append("frozen_fingerprint_mismatch")

    if any(
        _text(row.get("last_reported_run")) == run_key or _text(row.get("run_key")) == run_key
        for row in event_index_rows
    ):
        errors.append("shadow_eventindex_write_forbidden")
    return sorted(set(errors))


def evaluate_shadow_acceptance(
    *,
    report_date: str,
    run_key: str,
    attempt_id: str,
    cfg: Mapping[str, object],
    run_rows: Iterable[Mapping[str, object]],
    active_signals: Iterable[Mapping[str, object]],
    candidates: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
    worker_audit_rows: Iterable[Mapping[str, object]],
    daily_items: Iterable[Mapping[str, object]],
    event_index_rows: Iterable[Mapping[str, object]],
    required_routes: Mapping[str, set[str]],
    enforce_continuation: bool | None = None,
) -> AcceptanceResult:
    """Evaluate the read-only ledger portion of v11 Shadow operational acceptance.

    This validator deliberately does not inspect the private archived Google Doc
    body. Full natural acceptance therefore requires this ledger result plus the
    separate archive-body readback contract.
    """
    errors: list[str] = []
    warnings = ["archive_body_readback_external"]
    runs = [dict(row) for row in run_rows]
    signals = [dict(row) for row in active_signals]
    candidates_list = [dict(row) for row in candidates]
    coverage = [dict(row) for row in coverage_rows]
    audits = [dict(row) for row in worker_audit_rows]
    items = [dict(row) for row in daily_items]
    events = [dict(row) for row in event_index_rows]

    matching_runs = [
        row for row in runs
        if _text(row.get("run_key")) == run_key and _text(row.get("attempt_id")) == attempt_id
    ]
    if len(matching_runs) != 1:
        verdict = "INCOMPLETE" if not matching_runs else "FAIL"
        return AcceptanceResult(
            ledger_verdict=verdict,
            source_failure_path="NOT_EVALUATED",
            errors=("shadow_attempt_row_count_not_one",),
            warnings=tuple(warnings),
            metrics={"run_row_count": len(matching_runs)},
        )
    run = matching_runs[0]
    if not _text(run.get("completed_at_bjt")):
        return AcceptanceResult(
            ledger_verdict="INCOMPLETE",
            source_failure_path="NOT_EVALUATED",
            errors=("shadow_attempt_not_completed",),
            warnings=tuple(warnings),
            metrics={"run_row_count": 1},
        )

    if _text(run.get("report_date")) != report_date:
        errors.append("run_report_date_mismatch")
    if _text(run.get("canonical_attempt")):
        errors.append("shadow_attempt_must_not_be_canonical")
    if _text(run.get("transaction_id")) != attempt_id:
        errors.append("transaction_id_mismatch")
    if not _text(run.get("schema_version")).startswith("v11."):
        errors.append("run_schema_version_not_v11")

    final_expectations = {
        "stage": "completed",
        "final_status": "shadow_passed",
        "state_status": "passed",
        "delivery_status": "delivered",
        "resume_stage": "passed",
    }
    for field, expected in final_expectations.items():
        if _text(run.get(field)) != expected:
            errors.append(f"final_state_mismatch:{field}")
    if not _boolish(run.get("readback_match")):
        errors.append("readback_match_not_true")
    if _text(run.get("write_status")) != "success":
        errors.append("write_status_not_success")
    if _text(run.get("readback_status")) not in {"success", "passed"}:
        errors.append("readback_status_not_success")

    if _int(run.get("candidate_count")) != len(candidates_list):
        errors.append("candidate_count_mismatch")
    if _int(run.get("verified_count")) != len(candidates_list):
        errors.append("verified_count_mismatch")

    coverage_confidence = _text(run.get("coverage_confidence")).upper()
    pre_coverage = _text(run.get("coverage_confidence_pre_rescue")).upper()
    if coverage_confidence not in VALID_COVERAGE:
        errors.append("invalid_final_coverage_confidence")
    if pre_coverage not in VALID_COVERAGE:
        errors.append("invalid_pre_rescue_coverage_confidence")
    if pre_coverage == "LOW" and not _boolish(run.get("rescue_triggered")):
        errors.append("low_pre_rescue_without_rescue")

    barrier_errors = validate_structured_snapshot_barrier(
        run_key=run_key,
        report_date=report_date,
        coverage_rows=coverage,
        expected_collector_ids=barrier_required_structured_collector_ids(cfg),
        not_before_bjt=cfg.get("collector_snapshot_not_before_bjt", "18:00:00"),
        current_active_signal_count=len(signals),
        declared_signal_count=run.get("signal_count"),
    )
    errors.extend(barrier_errors)

    channel_health = _channel_health(run)
    if not channel_health:
        errors.append("channel_health_missing_or_invalid")
    errors.extend(
        validate_unified_ingestion_snapshot(
            run_key=run_key,
            attempt_id=attempt_id,
            active_signals=signals,
            candidates=candidates_list,
            coverage_rows=coverage,
            required_routes=required_routes,
            channel_health=channel_health,
        )
    )

    max_audit_rows = max(0, _int(cfg.get("worker_route_audit_max_result_rows_per_route"), 5))
    audit_errors, audit_metrics = _worker_audit_errors(
        run_key=run_key,
        attempt_id=attempt_id,
        required_routes=required_routes,
        active_signals=signals,
        coverage_rows=coverage,
        audit_rows=audits,
        max_result_rows=max_audit_rows,
    )
    errors.extend(audit_errors)

    errors.extend(
        _manifest_errors(
            run_key=run_key,
            attempt_id=attempt_id,
            run=run,
            candidates=candidates_list,
            daily_items=items,
            event_index_rows=events,
            max_items=max(0, _int(cfg.get("max_items"), 12)),
        )
    )

    failed_collectors = [
        row
        for row in coverage
        if _text(row.get("run_key")) == run_key
        and _text(row.get("producer_id")).startswith("collector/")
        and _text(row.get("execution_status")) in {"failed", "skipped"}
    ]
    worker_coverage = [
        row
        for row in coverage
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
    ]
    try:
        policy_date = date.fromisoformat(report_date)
    except ValueError:
        policy_date = CONTINUATION_POLICY_EFFECTIVE_DATE
        errors.append("invalid_report_date")
    continuation_is_required = (
        bool(enforce_continuation)
        if enforce_continuation is not None
        else policy_date >= CONTINUATION_POLICY_EFFECTIVE_DATE
    )
    if not failed_collectors:
        source_failure_path = "NOT_EXERCISED"
    elif not continuation_is_required:
        source_failure_path = "NOT_ENFORCED_PRE_EFFECTIVE_DATE"
    elif worker_coverage:
        source_failure_path = "PASS"
    else:
        source_failure_path = "FAIL"
        errors.append("SOURCE_FAILURE_WITHOUT_WORKER_CONTINUATION")

    unique_errors = tuple(sorted(set(errors)))
    structured_signal_count = sum(
        1 for row in signals if _text(row.get("producer_id")).startswith("collector/")
    )
    worker_signal_count = sum(
        1 for row in signals
        if _text(row.get("origin_attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
    )
    metrics: dict[str, object] = {
        "active_signal_count": len(signals),
        "structured_signal_count": structured_signal_count,
        "worker_signal_count": worker_signal_count,
        "candidate_count": len(candidates_list),
        "frozen_item_count": len([
            row for row in items
            if _text(row.get("run_key")) == run_key and _text(row.get("attempt_id")) == attempt_id
        ]),
        "structured_collector_count": len(barrier_required_structured_collector_ids(cfg)),
        "failed_or_skipped_collector_count": len(failed_collectors),
        "worker_or_rescue_coverage_count": len(worker_coverage),
        "coverage_confidence": coverage_confidence,
        "archive_check": "EXTERNAL_REQUIRED",
        **audit_metrics,
    }
    return AcceptanceResult(
        ledger_verdict="PASS" if not unique_errors else "FAIL",
        source_failure_path=source_failure_path,
        errors=unique_errors,
        warnings=tuple(warnings),
        metrics=metrics,
    )
