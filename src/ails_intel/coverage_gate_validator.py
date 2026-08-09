from __future__ import annotations

import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.coverage_gate import validate_gate_snapshot
from ails_intel.runtime import build_run_key, load_active_config
from ails_intel.safe_logger import log_event
from ails_intel.state.sheets import SheetsStore


def _target_datetime(date_text: str, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if not date_text:
        return datetime.now(tz)
    parsed = datetime.strptime(date_text, "%Y-%m-%d")
    return parsed.replace(hour=12, tzinfo=tz)


def _attempt_number(attempt_id: str) -> int:
    tail = str(attempt_id).rsplit("-A", 1)
    return int(tail[1]) if len(tail) == 2 and tail[1].isdigit() else -1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--attempt", default="")
    args = parser.parse_args()

    service = build_sheets_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    cfg = load_active_config(store)
    if str(cfg["execution_mode"].value) != "shadow":
        log_event("coverage_gate_validation", component="coverage_gate_validator", stage="precheck", status="FAIL", error_code="NOT_SHADOW_MODE", error_count=1)
        raise SystemExit(1)

    target = _target_datetime(args.date, str(cfg["timezone"].value))
    run_key = build_run_key(cfg, target)
    all_runs = store.run_rows(run_key)
    if args.attempt:
        attempt_id = args.attempt.strip()
    else:
        attempts = [str(row.get("attempt_id", "")).strip() for row in all_runs if str(row.get("attempt_id", "")).strip()]
        attempt_id = max(attempts, key=_attempt_number) if attempts else ""

    run_rows = store.run_rows(run_key, attempt_id) if attempt_id else []
    if len(run_rows) != 1:
        log_event(
            "coverage_gate_validation", component="coverage_gate_validator", stage="precheck",
            status="FAIL", run_key=run_key, attempt_id=attempt_id,
            error_code="RUN_ROW_COUNT_NOT_ONE", error_count=1, rows_found=len(run_rows),
        )
        raise SystemExit(1)

    run = run_rows[0]
    try:
        health = json.loads(str(run.get("channel_health_json", "") or "{}"))
    except json.JSONDecodeError:
        health = {}

    mandatory = [str(x) for x in cfg["mandatory_channels_json"].value]
    daily = store.daily_item_rows(run_key)
    events = store.event_index_rows()
    event_owners = sum(
        1 for row in events
        if str(row.get("last_reported_run", "")).strip() == run_key
        or str(row.get("run_key", "")).strip() == run_key
    )

    errors = validate_gate_snapshot(
        run=run,
        mandatory_channels=mandatory,
        channel_health=health,
        daily_items_for_run=len(daily),
        event_index_ownership_count=event_owners,
    )

    log_event(
        "coverage_gate_validation",
        component="coverage_gate_validator",
        stage="pre_freeze_gate",
        status="PASS" if not errors else "FAIL",
        run_key=run_key,
        attempt_id=attempt_id,
        check_count=12,
        rows_found=len(store.coverage_rows(run_key)),
        error_count=len(errors),
        error_code="" if not errors else ";".join(errors),
    )
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
