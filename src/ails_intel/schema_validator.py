from __future__ import annotations

from .auth import build_sheets_service, spreadsheet_id_from_env
from .config_loader import parse_active_config
from .safe_logger import log_event
from .schema_manifest import EXPECTED_HEADERS, MIN_GRID, REQUIRED_V11_CONFIG, VALIDATION_PROBES


def _value_rows(service, spreadsheet_id: str, a1_range: str):
    return service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=a1_range
    ).execute().get("values", [])


def _validation_values(cell: dict) -> set[str]:
    rule = cell.get("dataValidation") or {}
    condition = rule.get("condition") or {}
    values = condition.get("values") or []
    return {str(v.get("userEnteredValue", "")) for v in values}


def validate() -> list[str]:
    errors: list[str] = []
    service = build_sheets_service()
    sid = spreadsheet_id_from_env()

    meta = service.spreadsheets().get(
        spreadsheetId=sid,
        fields="sheets(properties(title,gridProperties(rowCount,columnCount,frozenRowCount)))",
    ).execute()
    sheets = {s["properties"]["title"]: s["properties"] for s in meta.get("sheets", [])}

    for title, expected in EXPECTED_HEADERS.items():
        if title not in sheets:
            errors.append(f"missing_sheet:{title}")
            continue
        rows = _value_rows(service, sid, f"{title}!1:1")
        actual = rows[0] if rows else []
        if actual != expected:
            errors.append(f"header_mismatch:{title}")

    for title, minimums in MIN_GRID.items():
        props = sheets.get(title)
        if not props:
            continue
        grid = props.get("gridProperties", {})
        for field, minimum in minimums.items():
            if int(grid.get(field, 0)) < minimum:
                errors.append(f"grid_too_small:{title}:{field}")

    config_rows = _value_rows(service, sid, "Lite_Config!A:G")
    try:
        cfg = parse_active_config(config_rows)
    except ValueError:
        errors.append("config_parse_error")
        cfg = {}

    missing_cfg = REQUIRED_V11_CONFIG - set(cfg)
    if missing_cfg:
        errors.append(f"missing_v11_config_count:{len(missing_cfg)}")

    if cfg:
        if cfg.get("execution_mode") and cfg["execution_mode"].value != "shadow":
            errors.append("execution_mode_not_shadow")
        if cfg.get("system_version") and cfg["system_version"].value != "v11.0-EventIntel-A1":
            errors.append("unexpected_system_version")
        weights = [
            cfg.get("score_weight_materiality"),
            cfg.get("score_weight_investment_relevance"),
            cfg.get("score_weight_evidence"),
            cfg.get("score_weight_novelty"),
        ]
        if all(weights):
            total = sum(float(x.value) for x in weights)
            if abs(total - 1.0) > 1e-9:
                errors.append("score_weights_invalid")
        try:
            channel_ids = {x["id"] for x in cfg["channels_json"].value}
            mandatory = set(cfg["mandatory_channels_json"].value)
            if not mandatory.issubset(channel_ids):
                errors.append("mandatory_channel_config_invalid")
        except Exception:
            errors.append("channel_config_parse_error")

    probe_resp = service.spreadsheets().get(
        spreadsheetId=sid,
        ranges=list(VALIDATION_PROBES),
        includeGridData=True,
        fields="sheets(properties(title),data(startRow,startColumn,rowData(values(dataValidation))))",
    ).execute()

    found = {}
    for sheet in probe_resp.get("sheets", []):
        title = sheet.get("properties", {}).get("title")
        for data in sheet.get("data", []):
            sr, sc = data.get("startRow", 0), data.get("startColumn", 0)
            rows = data.get("rowData", [])
            if not rows or not rows[0].get("values"):
                continue
            cell = rows[0]["values"][0]
            n = sc + 1
            letters = ""
            while n:
                n, rem = divmod(n - 1, 26)
                letters = chr(65 + rem) + letters
            found[f"{title}!{letters}{sr + 1}"] = _validation_values(cell)

    for a1, expected_values in VALIDATION_PROBES.items():
        if found.get(a1, set()) != expected_values:
            errors.append(f"validation_mismatch:{a1}")

    return errors


def main():
    errors = validate()
    log_event(
        "schema_validation",
        component="schema_validator",
        status="PASS" if not errors else "FAIL",
        error_count=len(errors),
    )
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
