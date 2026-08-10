from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.runtime import load_active_config
from ails_intel.safe_logger import log_event
from ails_intel.state.sheets import SheetsStore
from ails_intel.unified_ingestion import (
    WORKER_PRODUCERS,
    compact_manifest_hash,
    enabled_structured_collector_ids,
    required_worker_routes,
    validate_structured_snapshot_barrier,
    validate_unified_ingestion_snapshot,
)

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


def _enabled(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "off"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Beijing report date YYYY-MM-DD")
    parser.add_argument("--attempt", help="Fully-qualified attempt ID")
    args = parser.parse_args()

    service = build_sheets_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    raw_cfg = load_active_config(store)
    cfg = {key: entry.value for key, entry in raw_cfg.items()}
    tz = ZoneInfo(str(cfg.get("timezone", "Asia/Shanghai")))
    report_date = args.date or datetime.now(tz).date().isoformat()
    run_key = _run_key(cfg, report_date)

    run_rows = store.run_rows(run_key)
    attempt_id = str(args.attempt or _latest_attempt(run_rows)).strip()
    if not attempt_id:
        log_event(
            "unified_ingestion_validation",
            component="unified_ingestion_validator",
            stage="sprint4",
            status="FAIL",
            run_key=run_key,
            error_code="NO_SHADOW_ATTEMPT",
            error_count=1,
        )
        raise SystemExit(1)

    matching_runs = [row for row in run_rows if str(row.get("attempt_id", "")).strip() == attempt_id]
    if len(matching_runs) != 1:
        log_event(
            "unified_ingestion_validation",
            component="unified_ingestion_validator",
            stage="sprint4",
            status="FAIL",
            run_key=run_key,
            attempt_id=attempt_id,
            error_code="ATTEMPT_ROW_COUNT",
            error_count=1,
        )
        raise SystemExit(1)

    run = matching_runs[0]
    entity_rows = store.dict_rows("Entities!A:V")
    required = required_worker_routes(cfg, entity_rows)
    active_signals = store.active_signals(run_key)
    candidates = store.candidate_rows(run_key, attempt_id)
    coverage = store.coverage_rows(run_key)

    try:
        channel_health = json.loads(str(run.get("channel_health_json", "") or "{}"))
    except json.JSONDecodeError:
        channel_health = {}

    errors = validate_unified_ingestion_snapshot(
        run_key=run_key,
        attempt_id=attempt_id,
        active_signals=active_signals,
        candidates=candidates,
        coverage_rows=coverage,
        required_routes=required,
        channel_health=channel_health,
    )

    if _enabled(cfg.get("collector_snapshot_barrier_enabled"), default=True):
        errors.extend(
            validate_structured_snapshot_barrier(
                run_key=run_key,
                report_date=report_date,
                coverage_rows=coverage,
                expected_collector_ids=enabled_structured_collector_ids(cfg),
                not_before_bjt=cfg.get("collector_snapshot_not_before_bjt", "18:00:00"),
                current_active_signal_count=len(active_signals),
                declared_signal_count=run.get("signal_count"),
            )
        )
        errors = sorted(set(errors))

    worker_signal_count = sum(
        1
        for row in active_signals
        if str(row.get("origin_attempt_id", "")).strip() == attempt_id
        and str(row.get("producer_id", "")).strip() in WORKER_PRODUCERS
    )
    worker_coverage_count = sum(
        1
        for row in coverage
        if str(row.get("attempt_id", "")).strip() == attempt_id
        and str(row.get("producer_id", "")).strip() in WORKER_PRODUCERS
    )
    route_count = sum(len(routes) for routes in required.values())
    log_event(
        "unified_ingestion_validation",
        component="unified_ingestion_validator",
        stage="sprint4",
        status="PASS" if not errors else "FAIL",
        run_key=run_key,
        attempt_id=attempt_id,
        signal_count=worker_signal_count,
        coverage_row_count=worker_coverage_count,
        route_count=route_count,
        candidate_count=len(candidates),
        error_count=len(errors),
        manifest_hash=compact_manifest_hash(required),
        error_code="" if not errors else errors[0],
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
