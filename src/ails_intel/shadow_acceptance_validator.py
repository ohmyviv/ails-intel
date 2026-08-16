from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.runtime import load_active_config
from ails_intel.safe_logger import log_event
from ails_intel.shadow_acceptance import evaluate_shadow_acceptance
from ails_intel.source_route_integrity import reconcile_due_source_routes
from ails_intel.source_schedule import due_source_route_ids
from ails_intel.state.sheets import SheetsStore
from ails_intel.unified_ingestion import required_worker_routes

ATTEMPT_RE = re.compile(r"-A(\d+)$")


def _latest_attempt(rows: list[dict[str, object]]) -> str:
    ranked: list[tuple[int, str]] = []
    for row in rows:
        attempt = str(row.get("attempt_id", "")).strip()
        match = ATTEMPT_RE.search(attempt)
        if match:
            ranked.append((int(match.group(1)), attempt))
    return max(ranked, default=(0, ""))[1]


def _run_key(cfg: dict[str, object], report_date: str) -> str:
    token = report_date.replace("-", "")
    hour = int(float(cfg.get("report_cutoff_hour_bjt", 20)))
    minute = int(float(cfg.get("report_cutoff_minute_bjt", 30)))
    prefix = str(cfg.get("shadow_run_prefix", "AILS11S"))
    return f"{prefix}-{token}-{hour:02d}{minute:02d}-BJT"


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only v11 Shadow post-run ledger acceptance validator"
    )
    parser.add_argument("--date", help="Beijing report date YYYY-MM-DD")
    parser.add_argument("--attempt", help="Fully-qualified Shadow attempt ID")
    parser.add_argument(
        "--enforce-continuation",
        action="store_true",
        help="Enforce source-failure -> Worker continuation even before the 2026-08-15 natural-policy date",
    )
    args = parser.parse_args()

    service = build_sheets_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    active_cfg = load_active_config(store)
    cfg = {key: entry.value for key, entry in active_cfg.items()}
    tz = ZoneInfo(str(cfg.get("timezone", "Asia/Shanghai")))
    report_date = args.date or datetime.now(tz).date().isoformat()
    run_key = _run_key(cfg, report_date)

    run_rows = store.run_rows(run_key)
    attempt_id = str(args.attempt or _latest_attempt(run_rows)).strip()
    if not attempt_id:
        log_event(
            "shadow_acceptance_validation",
            component="shadow_acceptance_validator",
            stage="post_run",
            status="INCOMPLETE",
            run_key=run_key,
            ledger_verdict="INCOMPLETE",
            source_failure_path="NOT_EVALUATED",
            archive_check="EXTERNAL_REQUIRED",
            error_code="NO_SHADOW_ATTEMPT",
            error_count=1,
        )
        raise SystemExit(1)

    entity_rows = store.dict_rows("Entities!A:V")
    required = required_worker_routes(cfg, entity_rows)
    signals = store.active_signals(run_key)
    candidates = store.candidate_rows(run_key, attempt_id)
    coverage = store.coverage_rows(run_key)
    audits = store.dict_rows("Lite_WorkerAudit!A:AC")
    daily_items = store.daily_item_rows(run_key)
    event_index = store.event_index_rows()

    due_errors: list[str] = []
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
        due_errors.extend(due_check.errors)
        due_required_count = due_check.required_route_count
        due_completed_count = due_check.completed_route_count
        due_incomplete_count = due_check.incomplete_route_count

        matching_run = next(
            (
                row
                for row in run_rows
                if str(row.get("run_key", "")).strip() == run_key
                and str(row.get("attempt_id", "")).strip() == attempt_id
            ),
            {},
        )
        if due_incomplete_count and str(matching_run.get("coverage_confidence", "")).strip().upper() == "HIGH":
            due_errors.append("due_source_incomplete_but_coverage_high")

    result = evaluate_shadow_acceptance(
        report_date=report_date,
        run_key=run_key,
        attempt_id=attempt_id,
        cfg=cfg,
        run_rows=run_rows,
        active_signals=signals,
        candidates=candidates,
        coverage_rows=coverage,
        worker_audit_rows=audits,
        daily_items=daily_items,
        event_index_rows=event_index,
        required_routes=required,
        enforce_continuation=True if args.enforce_continuation else None,
    )
    metrics = result.metrics
    combined_errors = tuple(sorted(set(result.errors) | set(due_errors)))
    ledger_verdict = "PASS" if result.ledger_verdict == "PASS" and not combined_errors else "FAIL"
    log_event(
        "shadow_acceptance_validation",
        component="shadow_acceptance_validator",
        stage="post_run",
        status=ledger_verdict,
        run_key=run_key,
        attempt_id=attempt_id,
        ledger_verdict=ledger_verdict,
        source_failure_path=result.source_failure_path,
        archive_check=str(metrics.get("archive_check", "EXTERNAL_REQUIRED")),
        coverage_confidence=str(metrics.get("coverage_confidence", "")),
        signal_count=int(metrics.get("active_signal_count", 0) or 0),
        structured_signal_count=int(metrics.get("structured_signal_count", 0) or 0),
        worker_signal_count=int(metrics.get("worker_signal_count", 0) or 0),
        candidate_count=int(metrics.get("candidate_count", 0) or 0),
        frozen_item_count=int(metrics.get("frozen_item_count", 0) or 0),
        route_count=int(metrics.get("required_worker_route_count", 0) or 0),
        coverage_row_count=int(metrics.get("worker_or_rescue_coverage_count", 0) or 0),
        due_source_required_count=due_required_count,
        due_source_completed_count=due_completed_count,
        due_source_incomplete_count=due_incomplete_count,
        error_code="" if not combined_errors else combined_errors[0],
        error_count=len(combined_errors),
    )
    raise SystemExit(0 if ledger_verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
