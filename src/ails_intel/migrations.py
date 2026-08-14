from __future__ import annotations
import argparse
import json
import os
from collections.abc import Mapping
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
from ails_intel.schema_manifest import EXPECTED_HEADERS, VALIDATION_PROBES

BJT = ZoneInfo("Asia/Shanghai")

SEARCH_PLAN_HEADERS = (
    "plan_id", "lane", "region", "language", "priority", "query_template",
    "cadence", "notes", "status", "source_scope", "event_types", "time_window",
    "exclusion_terms", "first_seen_only", "last_reviewed", "version",
)

@dataclass(frozen=True)
class ConfigUpsert:
    key: str
    value: str
    value_type: str
    notes: str
    owner: str = "v11-sprint4.6"

@dataclass(frozen=True)
class ConfigJsonMapListExtend:
    key: str
    map_key: str
    values: tuple[str, ...]

@dataclass(frozen=True)
class ValidationRule:
    column_index: int
    values: tuple[str, ...]

@dataclass(frozen=True)
class SheetSpec:
    title: str
    headers: tuple[str, ...]
    row_count: int
    validations: tuple[ValidationRule, ...] = ()

@dataclass(frozen=True)
class RegistryRowUpsert:
    sheet_name: str
    headers: tuple[str, ...]
    key_column: str
    values: tuple[str, ...]

@dataclass(frozen=True)
class MigrationSpec:
    migration_id: str
    sheets: tuple[SheetSpec, ...] = ()
    config_upserts: tuple[ConfigUpsert, ...] = ()
    config_json_map_list_extends: tuple[ConfigJsonMapListExtend, ...] = ()
    registry_rows: tuple[RegistryRowUpsert, ...] = ()


def sprint_4_6_a1(_private_payload: Mapping[str, object] | None = None) -> MigrationSpec:
    disposition_col = CHALLENGER_HEADERS.index("disposition")
    miss_type_col = CHALLENGER_HEADERS.index("miss_type")
    severity_col = CHALLENGER_HEADERS.index("miss_severity")
    primary_status_col = CHALLENGER_HEADERS.index("primary_source_status")

    signal_headers = EXPECTED_HEADERS["Lite_Signals"]
    signal_validation_keys = (
        ("channel_id", "Lite_Signals!G2"),
        ("discovery_method", "Lite_Signals!J2"),
        ("priority_hint", "Lite_Signals!W2"),
        ("ai_core_hint", "Lite_Signals!X2"),
        ("life_science_core_hint", "Lite_Signals!Y2"),
        ("signal_state", "Lite_Signals!Z2"),
    )

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
            SheetSpec(
                title="Lite_Signals",
                headers=tuple(signal_headers),
                row_count=5000,
                validations=tuple(
                    ValidationRule(
                        signal_headers.index(column_name),
                        tuple(sorted(VALIDATION_PROBES[a1])),
                    )
                    for column_name, a1 in signal_validation_keys
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


def sprint_4_6_b1(private_payload: Mapping[str, object] | None = None) -> MigrationSpec:
    payload = private_payload or {}
    plans_raw = payload.get("search_plans")
    additions_raw = payload.get("worker_channel_plan_map_additions")
    if not isinstance(plans_raw, list) or len(plans_raw) != 3:
        raise ValueError("sprint_4_6_b1 requires exactly three private search_plans")
    if not isinstance(additions_raw, Mapping):
        raise ValueError("sprint_4_6_b1 requires worker_channel_plan_map_additions")

    rows: list[RegistryRowUpsert] = []
    plan_ids: list[str] = []
    for item in plans_raw:
        if not isinstance(item, Mapping):
            raise ValueError("search_plans entries must be objects")
        values = tuple(str(item.get(header, "")).strip() for header in SEARCH_PLAN_HEADERS)
        row = dict(zip(SEARCH_PLAN_HEADERS, values, strict=True))
        plan_id = row["plan_id"]
        if not plan_id or plan_id in plan_ids:
            raise ValueError("search_plans plan_id values must be unique and non-empty")
        if not row["query_template"]:
            raise ValueError(f"search plan {plan_id} requires private query_template")
        if row["priority"] != "P0" or row["cadence"] != "daily" or row["status"] != "active":
            raise ValueError(f"search plan {plan_id} must be active daily P0")
        if row["first_seen_only"].upper() != "TRUE":
            raise ValueError(f"search plan {plan_id} must be first_seen_only")
        rows.append(
            RegistryRowUpsert(
                sheet_name="SearchPlans",
                headers=SEARCH_PLAN_HEADERS,
                key_column="plan_id",
                values=values,
            )
        )
        plan_ids.append(plan_id)

    c1_raw = additions_raw.get("C1")
    if not isinstance(c1_raw, list):
        raise ValueError("worker_channel_plan_map_additions.C1 must be a list")
    c1_ids = tuple(str(value).strip() for value in c1_raw if str(value).strip())
    if set(c1_ids) != set(plan_ids) or len(c1_ids) != len(plan_ids):
        raise ValueError("C1 plan-map additions must exactly match private search_plans")

    return MigrationSpec(
        migration_id="sprint_4_6_b1",
        config_json_map_list_extends=(
            ConfigJsonMapListExtend(
                key="worker_channel_plan_map_json",
                map_key="C1",
                values=c1_ids,
            ),
        ),
        registry_rows=tuple(rows),
    )


MIGRATIONS = {
    "sprint_4_6_a1": sprint_4_6_a1,
    "sprint_4_6_b1": sprint_4_6_b1,
}
PRIVATE_PAYLOAD_MIGRATIONS = {"sprint_4_6_b1"}


def _load_private_payload(migration_id: str) -> Mapping[str, object] | None:
    if migration_id not in PRIVATE_PAYLOAD_MIGRATIONS:
        return None
    raw = os.environ.get("AILS_PRIVATE_MIGRATIONS_JSON", "").strip()
    if not raw:
        raise RuntimeError(f"{migration_id} requires AILS_PRIVATE_MIGRATIONS_JSON")
    try:
        root = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AILS_PRIVATE_MIGRATIONS_JSON is invalid JSON") from exc
    if not isinstance(root, Mapping):
        raise RuntimeError("AILS_PRIVATE_MIGRATIONS_JSON root must be an object")
    payload = root.get(migration_id)
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"private payload missing migration object: {migration_id}")
    return payload


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


def _column_letter(column_count: int) -> str:
    if column_count < 1:
        raise ValueError("column_count must be positive")
    out = ""
    value = column_count
    while value:
        value, remainder = divmod(value - 1, 26)
        out = chr(65 + remainder) + out
    return out


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
    validation_row_count = max(spec.row_count, int(grid.get("rowCount", 0)))
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
                            "endRowIndex": validation_row_count,
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


def _extend_config_json_map_lists(
    service,
    spreadsheet_id: str,
    extensions: Iterable[ConfigJsonMapListExtend],
    *,
    apply: bool,
) -> list[str]:
    rows = _rows(service, spreadsheet_id, "Lite_Config!A:G")
    if not rows:
        raise RuntimeError("Lite_Config is unavailable")
    by_key: dict[str, tuple[int, list[object]]] = {}
    for row_index, row in enumerate(rows[1:], start=2):
        padded = list(row) + [""] * 7
        key = str(padded[0]).strip()
        if key:
            if key in by_key:
                raise RuntimeError(f"duplicate Lite_Config key: {key}")
            by_key[key] = (row_index, padded)

    now = datetime.now(BJT).isoformat(timespec="seconds")
    writes: list[dict] = []
    changed: list[str] = []
    for extension in extensions:
        found = by_key.get(extension.key)
        if not found:
            raise RuntimeError(f"missing config for JSON extension: {extension.key}")
        row_index, row = found
        if str(row[2]).strip() != "json" or str(row[3]).strip().upper() != "TRUE":
            raise RuntimeError(f"config must be active json: {extension.key}")
        try:
            current = json.loads(str(row[1]))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSON config: {extension.key}") from exc
        if not isinstance(current, dict):
            raise RuntimeError(f"config JSON must be object: {extension.key}")
        existing = current.get(extension.map_key, [])
        if not isinstance(existing, list):
            raise RuntimeError(f"config JSON map value must be list: {extension.key}.{extension.map_key}")
        merged = list(existing)
        for value in extension.values:
            if value not in merged:
                merged.append(value)
        if merged == existing:
            continue
        current[extension.map_key] = merged
        rendered = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
        writes.extend(
            [
                {"range": f"Lite_Config!B{row_index}", "values": [[rendered]]},
                {"range": f"Lite_Config!F{row_index}", "values": [[now]]},
            ]
        )
        changed.append(extension.key)

    if apply and writes:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": writes},
        ).execute(num_retries=3)
    return changed


def _upsert_registry_rows(
    service,
    spreadsheet_id: str,
    upserts: Iterable[RegistryRowUpsert],
    *,
    apply: bool,
) -> list[str]:
    grouped: dict[tuple[str, tuple[str, ...], str], list[RegistryRowUpsert]] = {}
    for item in upserts:
        grouped.setdefault((item.sheet_name, item.headers, item.key_column), []).append(item)

    changed: list[str] = []
    writes: list[dict] = []
    for (sheet_name, headers, key_column), items in grouped.items():
        if key_column not in headers:
            raise RuntimeError(f"registry key column missing from headers: {sheet_name}.{key_column}")
        last_col = _column_letter(len(headers))
        rows = _rows(service, spreadsheet_id, f"{sheet_name}!A:{last_col}")
        if not rows:
            raise RuntimeError(f"registry sheet unavailable: {sheet_name}")
        actual_header = tuple(str(value) for value in rows[0])
        if actual_header != headers:
            raise RuntimeError(f"registry header mismatch: {sheet_name}")
        key_index = headers.index(key_column)
        by_key: dict[str, int] = {}
        for row_index, row in enumerate(rows[1:], start=2):
            padded = list(row) + [""] * len(headers)
            key = str(padded[key_index]).strip()
            if not key:
                continue
            if key in by_key:
                raise RuntimeError(f"duplicate registry key: {sheet_name}.{key}")
            by_key[key] = row_index

        next_row = len(rows) + 1
        for item in items:
            if len(item.values) != len(headers):
                raise RuntimeError(f"registry row width mismatch: {sheet_name}")
            key = str(item.values[key_index]).strip()
            if not key:
                raise RuntimeError(f"registry row requires key: {sheet_name}.{key_column}")
            row_index = by_key.get(key)
            if row_index:
                current = list(rows[row_index - 1]) + [""] * len(headers)
                stable_current = tuple(str(current[i]) for i in range(len(headers)))
                if stable_current == item.values:
                    continue
            else:
                row_index = next_row
                next_row += 1
            writes.append(
                {
                    "range": f"{sheet_name}!A{row_index}:{last_col}{row_index}",
                    "values": [list(item.values)],
                }
            )
            changed.append(f"{sheet_name}:{key}")

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

    for extension in spec.config_json_map_list_extends:
        row = values.get(extension.key)
        if not row:
            errors.append(f"missing_config:{extension.key}")
            continue
        padded = list(row) + [""] * 7
        try:
            current = json.loads(str(padded[1]))
        except json.JSONDecodeError:
            errors.append(f"config_invalid_json:{extension.key}")
            continue
        present = current.get(extension.map_key, []) if isinstance(current, dict) else []
        if not isinstance(present, list) or not set(extension.values).issubset(set(str(x) for x in present)):
            errors.append(f"config_json_extension_missing:{extension.key}.{extension.map_key}")

    grouped: dict[tuple[str, tuple[str, ...], str], list[RegistryRowUpsert]] = {}
    for item in spec.registry_rows:
        grouped.setdefault((item.sheet_name, item.headers, item.key_column), []).append(item)
    for (sheet_name, headers, key_column), items in grouped.items():
        last_col = _column_letter(len(headers))
        rows = _rows(service, spreadsheet_id, f"{sheet_name}!A:{last_col}")
        if not rows or tuple(str(value) for value in rows[0]) != headers:
            errors.append(f"registry_header_mismatch:{sheet_name}")
            continue
        key_index = headers.index(key_column)
        by_key: dict[str, list[tuple[str, ...]]] = {}
        for row in rows[1:]:
            padded = list(row) + [""] * len(headers)
            rendered = tuple(str(padded[i]) for i in range(len(headers)))
            key = rendered[key_index].strip()
            if key:
                by_key.setdefault(key, []).append(rendered)
        for item in items:
            key = item.values[key_index].strip()
            matches = by_key.get(key, [])
            if len(matches) != 1:
                errors.append(f"registry_key_count:{sheet_name}:{key}")
            elif matches[0] != item.values:
                errors.append(f"registry_row_mismatch:{sheet_name}:{key}")

    return sorted(set(errors))


def run_migration(migration_id: str, *, apply: bool) -> list[str]:
    factory = MIGRATIONS.get(migration_id)
    if factory is None:
        raise ValueError(f"unknown migration: {migration_id}")
    private_payload = _load_private_payload(migration_id)
    spec = factory(private_payload)
    service = build_sheets_service()
    spreadsheet_id = spreadsheet_id_from_env()

    sheet_actions = [
        _ensure_sheet(service, spreadsheet_id, sheet, apply=apply)
        for sheet in spec.sheets
    ]
    changed_configs = _upsert_config(service, spreadsheet_id, spec.config_upserts, apply=apply)
    changed_extensions = _extend_config_json_map_lists(
        service,
        spreadsheet_id,
        spec.config_json_map_list_extends,
        apply=apply,
    )
    changed_registry = _upsert_registry_rows(
        service,
        spreadsheet_id,
        spec.registry_rows,
        apply=apply,
    )

    errors = validate_migration(service, spreadsheet_id, spec) if apply else []
    log_event(
        "sheet_migration",
        component="migrations",
        stage=migration_id,
        status="PASS" if not errors else "FAIL",
        execution_status="apply" if apply else "preview",
        check_count=len(sheet_actions) + len(spec.registry_rows) + len(spec.config_json_map_list_extends),
        candidate_count=len(changed_configs) + len(changed_extensions) + len(changed_registry),
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
