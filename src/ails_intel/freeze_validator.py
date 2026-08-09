from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.freeze_contract import validate_shadow_freeze_snapshot
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
    if len(tail) == 2 and tail[1].isdigit():
        return int(tail[1])
    return -1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--attempt", default="")
    args = parser.parse_args()

    service = build_sheets_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    cfg = load_active_config(store)
    if str(cfg["execution_mode"].value) != "shadow":
        log_event("freeze_validation", component="freeze_validator", stage="precheck", status="FAIL", error_code="NOT_SHADOW_MODE", error_count=1)
        raise SystemExit(1)

    target = _target_datetime(args.date, str(cfg["timezone"].value))
    run_key = build_run_key(cfg, target)
    all_runs = store.run_rows(run_key)
    if args.attempt:
        attempt_id = args.attempt.strip()
    else:
        attempts = [str(row.get("attempt_id", "")).strip() for row in all_runs if str(row.get("attempt_id", "")).strip()]
        attempt_id = max(attempts, key=_attempt_number) if attempts else ""
    if not attempt_id:
        log_event("freeze_validation", component="freeze_validator", stage="precheck", status="FAIL", run_key=run_key, error_code="NO_SHADOW_ATTEMPT", error_count=1, rows_found=0)
        raise SystemExit(1)

    candidates = store.candidate_rows(run_key, attempt_id)
    daily_items = store.daily_item_rows(run_key)
    run_rows = store.run_rows(run_key, attempt_id)
    event_index_rows = store.event_index_rows()
    max_items = int(float(cfg["max_items"].value))

    errors = validate_shadow_freeze_snapshot(
        run_key=run_key,
        attempt_id=attempt_id,
        candidates=candidates,
        daily_items=daily_items,
        run_rows=run_rows,
        event_index_rows=event_index_rows,
        max_items=max_items,
    )
    log_event(
        "freeze_validation",
        component="freeze_validator",
        stage="shadow_freeze",
        status="PASS" if not errors else "FAIL",
        run_key=run_key,
        attempt_id=attempt_id,
        check_count=14,
        rows_found=len(daily_items),
        error_count=len(errors),
        error_code="" if not errors else ";".join(errors),
    )
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
