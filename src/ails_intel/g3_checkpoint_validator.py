from __future__ import annotations

import argparse
from datetime import date

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.runtime import load_active_config
from ails_intel.safe_logger import log_event
from ails_intel.source_route_integrity import reconcile_due_source_routes
from ails_intel.source_schedule import due_source_route_ids
from ails_intel.state.sheets import SheetsStore
from ails_intel.unified_ingestion import required_worker_routes
from ails_intel.worker_audit import validate_worker_audit_snapshot
from ails_intel.worker_checkpoint import build_g2_route_handoff


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only G3 validation from a persisted same-attempt G2 checkpoint"
    )
    parser.add_argument("--date", required=True, help="Beijing report date YYYY-MM-DD")
    parser.add_argument("--run-key", required=True, help="Explicit manual Shadow run_key")
    parser.add_argument("--attempt", required=True, help="Fully-qualified manual attempt ID")
    parser.add_argument(
        "--allow-legacy-g2-route-aliases",
        action="store_true",
        help="Allow the narrow sealed-G2 worker/broad/N compatibility bridge for historical checkpoints",
    )
    args = parser.parse_args()

    service = build_sheets_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    active_cfg = load_active_config(store)
    cfg = {key: entry.value for key, entry in active_cfg.items()}
    report_date = date.fromisoformat(args.date).isoformat()
    run_key = str(args.run_key).strip()
    attempt_id = str(args.attempt).strip()

    errors: list[str] = []
    if not run_key.startswith("AILS11M-"):
        errors.append("g3_checkpoint_requires_manual_shadow")
    if not attempt_id.startswith(f"{run_key}-A"):
        errors.append("g3_checkpoint_attempt_mismatch")
    if report_date.replace("-", "") not in run_key:
        errors.append("g3_checkpoint_report_date_mismatch")

    entity_rows = store.dict_rows("Entities!A:V")
    base_required = required_worker_routes(cfg, entity_rows)
    audits = store.dict_rows("Lite_WorkerAudit!A:AC")
    coverage = store.coverage_rows(run_key)
    signals = store.active_signals(run_key)

    due_routes: set[str] = set()
    due_required_count = 0
    due_completed_count = 0
    due_incomplete_count = 0
    if _enabled(cfg.get("worker_due_source_enforcement_enabled")):
        source_rows = store.dict_rows("SourceRegistry!A:AA")
        roles_raw = cfg.get("worker_due_source_roles_json", []) or []
        roles = roles_raw if isinstance(roles_raw, (list, tuple, set)) else []
        due_routes = due_source_route_ids(
            source_rows=source_rows,
            local_date=date.fromisoformat(report_date),
            allowed_roles=roles,
            required_priority=str(cfg.get("worker_due_source_priority", "P0")),
        )
        due_check = reconcile_due_source_routes(
            run_key=run_key,
            attempt_id=attempt_id,
            due_source_route_ids=due_routes,
            audit_rows=audits,
            coverage_rows=coverage,
        )
        errors.extend(due_check.errors)
        due_required_count = due_check.required_route_count
        due_completed_count = due_check.completed_route_count
        due_incomplete_count = due_check.incomplete_route_count

    handoff = build_g2_route_handoff(
        run_key=run_key,
        attempt_id=attempt_id,
        base_required_routes=base_required,
        due_source_route_ids=due_routes,
        audit_rows=audits,
        allow_legacy_broad_aliases=args.allow_legacy_g2_route_aliases,
    )
    errors.extend(handoff.errors)

    max_result_rows = int(float(cfg.get("worker_route_audit_max_result_rows_per_route", 5) or 5))
    errors.extend(
        validate_worker_audit_snapshot(
            run_key=run_key,
            attempt_id=attempt_id,
            audit_rows=audits,
            coverage_rows=coverage,
            active_signals=signals,
            required_routes=handoff.required_routes,
            max_result_rows_per_route=max_result_rows,
        )
    )
    errors = sorted(set(errors))

    base_route_count = sum(len(routes) for routes in base_required.values())
    final_route_count = sum(len(routes) for routes in handoff.required_routes.values())
    log_event(
        "g3_checkpoint_validation",
        component="g3_checkpoint_validator",
        stage="g3_checkpoint",
        status="PASS" if not errors else "FAIL",
        run_key=run_key,
        attempt_id=attempt_id,
        report_date=report_date,
        base_route_count=base_route_count,
        route_count=final_route_count,
        due_source_required_count=due_required_count,
        due_source_completed_count=due_completed_count,
        due_source_incomplete_count=due_incomplete_count,
        due_route_extension_count=handoff.due_extension_count,
        legacy_alias_count=handoff.legacy_alias_count,
        error_code="" if not errors else errors[0],
        error_count=len(errors),
    )
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
