from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from .auth import build_sheets_service, spreadsheet_id_from_env
from .config_loader import parse_active_config
from .safe_logger import log_event

ACCEPTED_LEGACY_FINAL = {"finished", "finished_partial_retrieval"}


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

    ok = all(check["ok"] for check in checks)
    log_event(
        "watchdog",
        component="watchdog",
        status="PASS" if ok else "FAIL",
        check_count=len(checks),
        error_count=sum(0 if check["ok"] else 1 for check in checks),
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
