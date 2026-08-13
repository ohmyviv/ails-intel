from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.challenger_audit import (
    CHALLENGER_DISPOSITIONS,
    CHALLENGER_HEADERS,
    MISS_SEVERITIES,
    MISS_TYPES,
    PRIMARY_SOURCE_STATUSES,
)
from ails_intel.safe_logger import log_event

BJT = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ConfigUpsert:
    key: str
    value: str
    value_type: str
    notes: str
    owner: str = "v11-sprint4.6"


@dataclass(frozen=True)
class ValidationRule:
    column_index: int  # zero-based
    values: tuple[str, ...]


@dataclass(frozen=True)
class SheetSpec:
    title: str
    headers: tuple[str, ...]
    row_count: int
    validations: tuple[ValidationRule, ...] = ()


@dataclass(frozen=True)
class MigrationSpec:
    migration_id: str
    sheets: tuple[SheetSpec, ...]
    config_upserts: tuple[ConfigUpsert, ...]


def sprint_4_6_a1() -> MigrationSpec:
    disposition_col = CHALLENGER_HEADERS.index("disposition")
    miss_type_col = CHALLENGER_HEADERS.index("miss_type")
    severity_col = CHALLENGER_HEADERS.index("miss_severity")
    primary_status_col = CHALLENGER_HEADERS.index("primary_source_status")
    return MigrationSpec(
        migration_id="sprint_4_6_a1",
        sheets=(
            SheetSpec(
                title="Lite_ChallengerAudit",
                headers=tuple(CHALLENGER_HEADERS),
                row_count=3000,
                validations=(
                    ValidationRule(disposition_col, tuple(sorted(CHALLENGER_DISPOSITIONS))),
                    ValidationRule(miss_type_col, tuple(sorted(MISS_TYPES))),
                    ValidationRule(severity_col, tuple(sorted(MISS_SEVERITIES))),
                    ValidationRule(primary_status_col, tuple(sorted(PRIMARY_SOURCE_STATUSES))),
                ),
            ),
        ),
        config_upserts=(
            ConfigUpsert(
                "challenger_audit_enabled",
                "TRUE",
                "bool",
                "Sprint 4.6 external challenger audit lane; audit-only and never a direct Candidate ingress",
            ),
            ConfigUpsert(
                "challenger_audit_blocking",
                "FALSE",
                "bool",
                "Sprint 4.6 probation mode: challenger findings do not block report delivery",
            ),
            ConfigUpsert(
                "challenger_disposition_enum",
                "|".join(sorted(CHALLENGER_DISPOSITIONS)),
                "enum",
                "Sprint 4.6 challenger terminal disposition taxonomy",
            ),
            ConfigUpsert(
                "challenger_primary_source_status_enum",
                "|".join(sorted(PRIMARY_SOURCE_STATUSES)),
                "enum",
                "Sprint 4.6 primary-source verification state",
            ),
            ConfigUpsert(
                "challenger_schema_version",
                "v11.2",
                "string",
                "Sprint 4.6 challenger audit schema version",
            ),
        ),
    )


MIGRATIONS = {"sprint_4_6_a1": sprint_4_6_a1}


def _sheet_map(service, spreadsheet_id: str) -> dict[str, dict]:
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title,gridProperties(rowCount,columnCount,frozenRowCount)))",
    ).execute(num_retries=3)
    return {s["properties"]["title"]: s["properties"] for s in meta.get("sheets", [])}


def _rows(service, spreadsheet_id: str, a1_range: str) -> list[list[object]]:
    return service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=a1_range
    ).execute(num_retries=3).get("values", [])


def _ensure_sheet(service, spreadsheet_id: str, spec: SheetSpec, *, apply: bool) -> dict:
    sheets = _sheet_map(service, spreadsheet_id)
    props = sheets.get(spec.title)
    required_cols = len(spec.headers)
    if props is None:
        if not apply:
            return {"action": "create_sheet", "title": spec.title}
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": spec.title,
                                "gridProperties": {
                                    "rowCount": spec.row_count,
                                    "columnCount": required_cols,
                                    "frozenRowCount": 1,
                                },
                            }
                        }
                    }
                ]
            },
        ).execute(num_retries=3)
        props = _sheet_map(service, spreadsheet_id)[spec.title]

    grid = props.get("gridProperties", {})
    resize: dict[str, int] = {}
    if int(grid.get("rowCount", 0)) < spec.row_count:
        resize["rowCount"] = spec.row_count
    if int(grid.get("columnCount", 0)) < required_cols:
        resize["columnCount"] = required_cols
    if int(grid.get("frozenRowCount", 0)) < 1:
        resize["frozenRowCount"] = 1
    if resize and apply:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": props["sheetId"], "gridProperties": resize},
                            "fields": ",".join(f"gridProperties.{key}" for key in resize),
                        }
                    }
                ]
            },
        ).execute(num_retries=3)

    current = _rows(service, spreadsheet_id, f"{spec.title}!1:1")
    current_header = [str(x) for x in (current[0] if current else [])]
    expected_header = list(spec.headers)
    if current_header != expected_header:
        if current_header and any(str(x).strip() for x in current_header):
            raise RuntimeError(f"refusing destructive header replacement for {spec.title}")
        if apply:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{spec.title}!A1",
                valueInputOption="RAW",
                body={"values": [expected_header]},
            ).execute(num_retries=3)

    if apply and spec.validations:
        requests = []
        for rule in spec.validations:
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": props["sheetId"],
                            "startRowIndex": 1,
                            "endRowIndex": spec.row_count,
                            "startColumnIndex": rule.column_index,
                            "endColumnIndex": rule.column_index + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": value} for value in rule.values],
                            },
                            "strict": True,
                            "showCustomUi": True,
                        },
                    }
                }
            )
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute(num_retries=3)

    return {"action": "verified" if current_header == expected_header else "ensure", "title": spec.title}


def _upsert_config(
    service,
    spreadsheet_id: str,
    upserts: Iterable[ConfigUpsert],
    *,
    apply: bool,
) -> list[str]:
    rows = _rows(service, spreadsheet_id, "Lite_Config!A:G")
    if not rows:
        raise RuntimeError("Lite_Config is unavailable")
    header = [str(x) for x in rows[0]]
    expected = ["config_key", "config_value", "value_type", "active", "notes", "updated_at_bjt", "owner"]
    if header[:7] != expected:
        raise RuntimeError("Lite_Config header mismatch")

    by_key: dict[str, int] = {}
    for row_index, row in enumerate(rows[1:], start=2):
        key = str(row[0]).strip() if row else ""
        if key:
            by_key[key] = row_index

    now = datetime.now(BJT).isoformat(timespec="seconds")
    changed: list[str] = []
    writes: list[dict] = []
    next_row = len(rows) + 1
    for item in upserts:
        desired = [item.key, item.value, item.value_type, "TRUE", item.notes, now, item.owner]
        row_index = by_key.get(item.key)
        if row_index:
            current = list(rows[row_index - 1]) + [""] * 7
            stable_current = [str(current[i]) for i in (0, 1, 2, 3, 4, 6)]
            stable_desired = [str(desired[i]) for i in (0, 1, 2, 3, 4, 6)]
            if stable_current == stable_desired:
                continue
        else:
            row_index = next_row
            next_row += 1
        writes.append({"range": f"Lite_Config!A{row_index}:G{row_index}", "values": [desired]})
        changed.append(item.key)

    if apply and writes:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": writes},
        ).execute(num_retries=3)
    return changed


def validate_migration(service, spreadsheet_id: str, spec: MigrationSpec) -> list[str]:
    errors: list[str] = []
    sheets = _sheet_map(service, spreadsheet_id)
    for sheet in spec.sheets:
        props = sheets.get(sheet.title)
        if not props:
            errors.append(f"missing_sheet:{sheet.title}")
            continue
        grid = props.get("gridProperties", {})
        if int(grid.get("rowCount", 0)) < sheet.row_count:
            errors.append(f"grid_too_small:{sheet.title}:rowCount")
        if int(grid.get("columnCount", 0)) < len(sheet.headers):
            errors.append(f"grid_too_small:{sheet.title}:columnCount")
        if int(grid.get("frozenRowCount", 0)) < 1:
            errors.append(f"grid_not_frozen:{sheet.title}")
        rows = _rows(service, spreadsheet_id, f"{sheet.title}!1:1")
        actual = [str(x) for x in (rows[0] if rows else [])]
        if actual != list(sheet.headers):
            errors.append(f"header_mismatch:{sheet.title}")

    config_rows = _rows(service, spreadsheet_id, "Lite_Config!A:G")
    values = {str(row[0]).strip(): row for row in config_rows[1:] if row and str(row[0]).strip()}
    for item in spec.config_upserts:
        row = values.get(item.key)
        if not row:
            errors.append(f"missing_config:{item.key}")
            continue
        padded = list(row) + [""] * 7
        if (
            str(padded[1]) != item.value
            or str(padded[2]) != item.value_type
            or str(padded[3]).upper() != "TRUE"
            or str(padded[4]) != item.notes
            or str(padded[6]) != item.owner
        ):
            errors.append(f"config_mismatch:{item.key}")
    return sorted(set(errors))


def run_migration(migration_id: str, *, apply: bool) -> list[str]:
    factory = MIGRATIONS.get(migration_id)
    if factory is None:
        raise ValueError(f"unknown migration: {migration_id}")
    spec = factory()
    service = build_sheets_service()
    spreadsheet_id = spreadsheet_id_from_env()

    sheet_actions = [
        _ensure_sheet(service, spreadsheet_id, sheet, apply=apply)
        for sheet in spec.sheets
    ]
    changed = _upsert_config(service, spreadsheet_id, spec.config_upserts, apply=apply)

    errors = validate_migration(service, spreadsheet_id, spec) if apply else []
    log_event(
        "sheet_migration",
        component="migrations",
        stage=migration_id,
        status="PASS" if not errors else "FAIL",
        execution_status="apply" if apply else "preview",
        check_count=len(sheet_actions),
        candidate_count=len(changed),
        error_count=len(errors),
    )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migration", required=True, choices=sorted(MIGRATIONS))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    errors = run_migration(args.migration, apply=args.apply)
    if errors:
        raise SystemExit("migration readback failed: " + ",".join(errors))


if __name__ == "__main__":
    main()
