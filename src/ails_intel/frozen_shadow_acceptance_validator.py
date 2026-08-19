from __future__ import annotations

import argparse
from datetime import date

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.candidate_lineage import validate_candidate_signal_lineage
from ails_intel.frozen_shadow_acceptance import project_frozen_structured_for_shadow_acceptance
from ails_intel.legacy_frozen_replay import qualify_legacy_frozen_structured_snapshot
from ails_intel.runtime import load_active_config
from ails_intel.safe_logger import log_event
from ails_intel.shadow_acceptance import evaluate_shadow_acceptance
from ails_intel.source_route_integrity import reconcile_due_source_routes
from ails_intel.source_schedule import due_source_route_ids
from ails_intel.state.sheets import SheetsStore
from ails_intel.structured_signal_identity import validate_structured_coverage_signal_identity
from ails_intel.unified_ingestion import required_worker_routes
from ails_intel.worker_checkpoint import build_g2_route_handoff


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _fail(*, run_key: str, attempt_id: str, error_code: str) -> None:
    log_event(
        "frozen_shadow_acceptance_validation",
        component="frozen_shadow_acceptance_validator",
        stage="post_run",
        status="FAIL",
        run_key=run_key,
        attempt_id=attempt_id,
        ledger_verdict="FAIL",
        source_failure_path="NOT_EVALUATED",
        archive_check="EXTERNAL_REQUIRED",
        error_code=error_code,
        error_count=1,
    )
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only final Shadow ledger acceptance for a manual Frozen Structured continuation"
    )
    parser.add_argument("--date", required=True, help="Beijing report date YYYY-MM-DD")
    parser.add_argument("--run-key", required=True, help="Explicit AILS11M manual run_key")
    parser.add_argument("--attempt", required=True, help="Fully-qualified manual attempt ID")
    parser.add_argument("--source-run-key", required=True, help="Immutable AILS11S Frozen Structured source run_key")
    parser.add_argument("--source-attempt", required=True, help="Frozen Structured source attempt ID")
    parser.add_argument(
        "--source-persisted-fingerprint",
        required=True,
        help="Fingerprint of the immutable legacy Structured rows exactly as persisted",
    )
    parser.add_argument(
        "--allow-legacy-g2-route-aliases",
        action="store_true",
        help="Allow the narrow sealed-G2 worker/broad/N bridge for historical manual checkpoints",
    )
    args = parser.parse_args()

    report_date = date.fromisoformat(args.date).isoformat()
    run_key = str(args.run_key).strip()
    attempt_id = str(args.attempt).strip()
    source_run_key = str(args.source_run_key).strip()
    source_attempt_id = str(args.source_attempt).strip()

    if not run_key.startswith("AILS11M-") or not attempt_id.startswith(f"{run_key}-A"):
        _fail(run_key=run_key, attempt_id=attempt_id, error_code="frozen_acceptance_manual_identity_invalid")
    if not source_run_key.startswith("AILS11S-") or not source_attempt_id.startswith(f"{source_run_key}-A"):
        _fail(run_key=run_key, attempt_id=attempt_id, error_code="frozen_acceptance_source_identity_invalid")
    if report_date.replace("-", "") not in run_key or report_date.replace("-", "") not in source_run_key:
        _fail(run_key=run_key, attempt_id=attempt_id, error_code="frozen_acceptance_report_date_mismatch")

    service = build_sheets_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    active_cfg = load_active_config(store)
    cfg = {key: entry.value for key, entry in active_cfg.items()}

    current_signals = store.active_signals(run_key)
    current_coverage = store.coverage_rows(run_key)
    source_signals = store.active_signals(source_run_key)
    source_coverage = store.coverage_rows(source_run_key)
    source_runs = store.run_rows(source_run_key)
    source_attempt_ids = [str(row.get("attempt_id", "")).strip() for row in source_runs]

    try:
        qualified = qualify_legacy_frozen_structured_snapshot(
            source_run_key=source_run_key,
            source_attempt_id=source_attempt_id,
            source_attempt_ids=source_attempt_ids,
            active_signals=source_signals,
            coverage_rows=source_coverage,
            expected_persisted_fingerprint=str(args.source_persisted_fingerprint).strip(),
        )
    except ValueError as exc:
        error_code = str(exc).split(";", 1)[0] or "legacy_frozen_source_qualification_failed"
        _fail(run_key=run_key, attempt_id=attempt_id, error_code=error_code)

    projection = project_frozen_structured_for_shadow_acceptance(
        run_key=run_key,
        source_run_key=source_run_key,
        source_attempt_id=source_attempt_id,
        qualified_source_signals=qualified.active_signals,
        qualified_source_coverage=qualified.coverage_rows,
        expected_qualified_fingerprint=qualified.qualified_fingerprint,
        current_active_signals=current_signals,
        current_coverage_rows=current_coverage,
    )
    if projection.errors:
        _fail(run_key=run_key, attempt_id=attempt_id, error_code=projection.errors[0])

    entity_rows = store.dict_rows("Entities!A:V")
    base_required = required_worker_routes(cfg, entity_rows)
    audit_rows = store.dict_rows("Lite_WorkerAudit!A:AC")

    due_routes: set[str] = set()
    due_errors: list[str] = []
    due_required_count = 0
    due_completed_count = 0
    due_incomplete_count = 0
    if _enabled(cfg.get("worker_due_source_enforcement_enabled")):
        source_registry_rows = store.dict_rows("SourceRegistry!A:AA")
        roles_raw = cfg.get("worker_due_source_roles_json", []) or []
        roles = roles_raw if isinstance(roles_raw, (list, tuple, set)) else []
        due_routes = due_source_route_ids(
            source_rows=source_registry_rows,
            local_date=date.fromisoformat(report_date),
            allowed_roles=roles,
            required_priority=str(cfg.get("worker_due_source_priority", "P0")),
        )
        due_check = reconcile_due_source_routes(
            run_key=run_key,
            attempt_id=attempt_id,
            due_source_route_ids=due_routes,
            audit_rows=audit_rows,
            coverage_rows=current_coverage,
        )
        due_errors.extend(due_check.errors)
        due_required_count = due_check.required_route_count
        due_completed_count = due_check.completed_route_count
        due_incomplete_count = due_check.incomplete_route_count

    handoff = build_g2_route_handoff(
        run_key=run_key,
        attempt_id=attempt_id,
        base_required_routes=base_required,
        due_source_route_ids=due_routes,
        audit_rows=audit_rows,
        allow_legacy_broad_aliases=args.allow_legacy_g2_route_aliases,
    )

    candidates = store.candidate_rows(run_key, attempt_id)
    daily_items = store.daily_item_rows(run_key)
    event_index = store.event_index_rows()
    run_rows = store.run_rows(run_key)

    identity_errors = validate_structured_coverage_signal_identity(
        run_key=run_key,
        coverage_rows=projection.coverage_rows,
        active_signals=projection.active_signals,
    )
    lineage_errors = validate_candidate_signal_lineage(
        candidates=candidates,
        active_signals=projection.active_signals,
    )

    result = evaluate_shadow_acceptance(
        report_date=report_date,
        run_key=run_key,
        attempt_id=attempt_id,
        cfg=cfg,
        run_rows=run_rows,
        active_signals=projection.active_signals,
        candidates=candidates,
        coverage_rows=projection.coverage_rows,
        worker_audit_rows=audit_rows,
        daily_items=daily_items,
        event_index_rows=event_index,
        required_routes=handoff.required_routes,
        enforce_continuation=True,
    )

    combined_errors = tuple(
        sorted(
            set(result.errors)
            | set(identity_errors)
            | set(lineage_errors)
            | set(due_errors)
            | set(handoff.errors)
        )
    )
    ledger_verdict = "PASS" if result.ledger_verdict == "PASS" and not combined_errors else "FAIL"
    metrics = result.metrics
    base_route_count = sum(len(routes) for routes in base_required.values())
    final_route_count = sum(len(routes) for routes in handoff.required_routes.values())

    log_event(
        "frozen_shadow_acceptance_validation",
        component="frozen_shadow_acceptance_validator",
        stage="post_run",
        status=ledger_verdict,
        run_key=run_key,
        attempt_id=attempt_id,
        ledger_verdict=ledger_verdict,
        source_failure_path=result.source_failure_path,
        archive_check="EXTERNAL_REQUIRED",
        coverage_confidence=str(metrics.get("coverage_confidence", "")),
        signal_count=int(metrics.get("active_signal_count", 0) or 0),
        structured_signal_count=int(metrics.get("structured_signal_count", 0) or 0),
        worker_signal_count=int(metrics.get("worker_signal_count", 0) or 0),
        candidate_count=int(metrics.get("candidate_count", 0) or 0),
        frozen_item_count=int(metrics.get("frozen_item_count", 0) or 0),
        base_route_count=base_route_count,
        route_count=final_route_count,
        coverage_row_count=int(metrics.get("worker_or_rescue_coverage_count", 0) or 0),
        due_source_required_count=due_required_count,
        due_source_completed_count=due_completed_count,
        due_source_incomplete_count=due_incomplete_count,
        due_route_extension_count=handoff.due_extension_count,
        legacy_alias_count=handoff.legacy_alias_count,
        error_code="" if not combined_errors else combined_errors[0],
        error_count=len(combined_errors),
    )
    raise SystemExit(0 if ledger_verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
