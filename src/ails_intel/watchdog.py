from __future__ import annotations

import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .auth import build_sheets_service, spreadsheet_id_from_env
from .config_loader import parse_active_config
from .safe_logger import log_event
from .snapshot_policy import (
    barrier_required_structured_collector_ids,
    validate_structured_snapshot_barrier,
)

ACCEPTED_LEGACY_FINAL = {"finished", "finished_partial_retrieval"}
CONTINUATION_POLICY_EFFECTIVE_DATE = date(2026, 8, 15)


def _rows(service, sid, rng):
    return service.spreadsheets().values().get(
        spreadsheetId=sid, range=rng
    ).execute().get("values", [])


def _boolish(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _index_rows(rows):
    if not rows:
        return [], {}
    header = rows[0]
    pos = {h: i for i, h in enumerate(header)}
    normalized = []
    for row in rows[1:]:
        normalized.append(list(row) + [""] * max(0, len(header) - len(row)))
    return normalized, pos


def _row_dict(row, pos):
    return {name: row[idx] if idx < len(row) else "" for name, idx in pos.items()}


def _healthy_attempt(row, pos) -> bool:
    state = str(row[pos["state_status"]]) if "state_status" in pos else ""
    readback = row[pos["readback_match"]] if "readback_match" in pos else ""
    final = str(row[pos["final_status"]]) if "final_status" in pos else ""
    if state == "passed" and _boolish(readback):
        return True
    return final in ACCEPTED_LEGACY_FINAL


def _check_run(rows, pos, run_key: str):
    matches = [r for r in rows if str(r[pos["run_key"]]) == run_key]
    healthy = [r for r in matches if _healthy_attempt(r, pos)]
    return {"run_key": run_key, "rows_found": len(matches), "healthy_rows": len(healthy), "ok": bool(healthy)}


def _attempt_number(attempt_id: str) -> int:
    tail = str(attempt_id).rsplit("-A", 1)
    return int(tail[1]) if len(tail) == 2 and tail[1].isdigit() else -1


def _shadow_continuation_check(*, run_rows, run_pos, coverage_rows, coverage_pos, cfg, day, suffix):
    """Detect a completed Shadow that stopped only because one source failed.

    The invariant is prospective from 2026-08-15 so the frozen 2026-08-14
    incident remains historical evidence rather than becoming a retroactive
    watchdog failure.
    """
    shadow_key = f'{cfg["shadow_run_prefix"].value}-{day.strftime("%Y%m%d")}-{suffix}'
    if day < CONTINUATION_POLICY_EFFECTIVE_DATE:
        return {"run_key": shadow_key, "evaluated": False, "ok": True, "failed_collectors": 0, "worker_rows": 0, "error_code": ""}

    matches = [r for r in run_rows if str(r[run_pos.get("run_key", -1)]) == shadow_key]
    if not matches:
        return {"run_key": shadow_key, "evaluated": False, "ok": True, "failed_collectors": 0, "worker_rows": 0, "error_code": ""}

    attempt_idx = run_pos.get("attempt_id")
    run = max(matches, key=lambda row: _attempt_number(str(row[attempt_idx])) if attempt_idx is not None else -1)
    completed_idx = run_pos.get("completed_at_bjt")
    if completed_idx is None or not str(run[completed_idx]).strip():
        return {"run_key": shadow_key, "evaluated": False, "ok": True, "failed_collectors": 0, "worker_rows": 0, "error_code": ""}

    attempt_id = str(run[attempt_idx]).strip() if attempt_idx is not None else ""
    coverage = [_row_dict(row, coverage_pos) for row in coverage_rows]
    raw_cfg = {key: entry.value for key, entry in cfg.items()}
    barrier_errors = validate_structured_snapshot_barrier(
        run_key=shadow_key,
        report_date=day.isoformat(),
        coverage_rows=coverage,
        expected_collector_ids=barrier_required_structured_collector_ids(raw_cfg),
        not_before_bjt=raw_cfg.get("collector_snapshot_not_before_bjt", "18:00:00"),
    )
    if barrier_errors:
        return {
            "run_key": shadow_key,
            "evaluated": False,
            "ok": True,
            "failed_collectors": 0,
            "worker_rows": 0,
            "error_code": barrier_errors[0],
        }

    failed_collectors = sum(
        1
        for row in coverage
        if str(row.get("run_key", "")).strip() == shadow_key
        and str(row.get("producer_id", "")).strip().startswith("collector/")
        and str(row.get("execution_status", "")).strip() in {"failed", "skipped"}
    )
    worker_rows = sum(
        1
        for row in coverage
        if str(row.get("run_key", "")).strip() == shadow_key
        and str(row.get("attempt_id", "")).strip() == attempt_id
        and str(row.get("producer_id", "")).strip() in {"chatgpt/worker", "chatgpt/rescue"}
    )
    ok = failed_collectors == 0 or worker_rows > 0
    return {
        "run_key": shadow_key,
        "evaluated": True,
        "ok": ok,
        "failed_collectors": failed_collectors,
        "worker_rows": worker_rows,
        "error_code": "" if ok else "SOURCE_FAILURE_WITHOUT_WORKER_CONTINUATION",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-shadow", action="store_true")
    parser.add_argument("--date", help="YYYY-MM-DD in configured timezone; defaults to today")
    args = parser.parse_args()

    service = build_sheets_service()
    sid = spreadsheet_id_from_env()
    cfg = parse_active_config(_rows(service, sid, "Lite_Config!A:G"))
    tz = ZoneInfo(str(cfg["timezone"].value))
    day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(tz).date()
    cutoff_h = int(float(cfg["report_cutoff_hour_bjt"].value))
    cutoff_m = int(float(cfg["report_cutoff_minute_bjt"].value))
    suffix = f"{cutoff_h:02d}{cutoff_m:02d}-BJT"

    run_rows, pos = _index_rows(_rows(service, sid, "Lite_Runs!A:BN"))
    if "run_key" not in pos:
        log_event("watchdog", component="watchdog", status="FAIL", error_code="RUN_KEY_COLUMN_MISSING")
        raise SystemExit(1)

    coverage_rows, coverage_pos = _index_rows(_rows(service, sid, "Lite_SourceCoverage!A:AD"))
    date_token = day.strftime("%Y%m%d")
    run_keys = [f'{cfg["production_run_prefix"].value}-{date_token}-{suffix}']
    if args.require_shadow:
        run_keys.append(f'{cfg["shadow_run_prefix"].value}-{date_token}-{suffix}')

    checks = [_check_run(run_rows, pos, run_key) for run_key in run_keys]
    for check in checks:
        log_event(
            "watchdog_check",
            component="watchdog",
            status="PASS" if check["ok"] else "FAIL",
            run_key=check["run_key"],
            rows_found=check["rows_found"],
            healthy_rows=check["healthy_rows"],
        )

    continuation = _shadow_continuation_check(
        run_rows=run_rows,
        run_pos=pos,
        coverage_rows=coverage_rows,
        coverage_pos=coverage_pos,
        cfg=cfg,
        day=day,
        suffix=suffix,
    )
    if continuation["evaluated"] or continuation["error_code"]:
        log_event(
            "watchdog_shadow_continuation",
            component="watchdog",
            status="PASS" if continuation["ok"] else "FAIL",
            run_key=continuation["run_key"],
            collector_failure_count=continuation["failed_collectors"],
            rows_found=continuation["worker_rows"],
            error_code=continuation["error_code"],
            error_count=0 if continuation["ok"] else 1,
        )

    ok = all(check["ok"] for check in checks) and continuation["ok"]
    log_event(
        "watchdog",
        component="watchdog",
        status="PASS" if ok else "FAIL",
        check_count=len(checks) + (1 if continuation["evaluated"] else 0),
        error_count=sum(0 if check["ok"] else 1 for check in checks) + (0 if continuation["ok"] else 1),
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
