from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.migrations import MIGRATIONS, PRIVATE_PAYLOAD_MIGRATIONS, run_migration

PRIVATE_CONFIG_PREFIX = "private_migration_"
PRIVATE_CONFIG_SUFFIX = "_json"


def _truthy(value: object) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES"}


def extract_private_payload_json(
    rows: list[list[object]], migration_id: str
) -> str:
    key = f"{PRIVATE_CONFIG_PREFIX}{migration_id}{PRIVATE_CONFIG_SUFFIX}"
    matches: list[list[object]] = []
    for row in rows[1:]:
        padded = list(row) + [""] * 7
        if str(padded[0]).strip() == key:
            matches.append(padded)
    if len(matches) != 1:
        raise RuntimeError(f"private migration payload key count must be 1: {key}")

    row = matches[0]
    if str(row[2]).strip() != "json" or not _truthy(row[3]):
        raise RuntimeError(f"private migration payload must be active json: {key}")
    raw = str(row[1]).strip()
    if not raw:
        raise RuntimeError(f"private migration payload is empty: {key}")
    try:
        root = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"private migration payload is invalid json: {key}") from exc
    if not isinstance(root, Mapping) or not isinstance(root.get(migration_id), Mapping):
        raise RuntimeError(f"private migration payload missing object: {migration_id}")
    return raw


def load_private_payload_from_sheet(migration_id: str) -> str:
    service = build_sheets_service()
    spreadsheet_id = spreadsheet_id_from_env()
    rows = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="Lite_Config!A:G")
        .execute(num_retries=3)
        .get("values", [])
    )
    if not rows:
        raise RuntimeError("Lite_Config is unavailable")
    return extract_private_payload_json(rows, migration_id)


def load_request(path: str) -> tuple[str, bool]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("migration request is unreadable or invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("migration request root must be an object")
    if str(payload.get("request_version", "")) != "v1":
        raise RuntimeError("unsupported migration request_version")
    migration_id = str(payload.get("migration", "")).strip()
    if migration_id not in MIGRATIONS:
        raise RuntimeError(f"unknown migration request: {migration_id}")
    apply = payload.get("apply")
    if not isinstance(apply, bool):
        raise RuntimeError("migration request apply must be boolean")
    return migration_id, apply


def run_request(path: str) -> list[str]:
    migration_id, apply = load_request(path)
    if migration_id in PRIVATE_PAYLOAD_MIGRATIONS and not os.environ.get(
        "AILS_PRIVATE_MIGRATIONS_JSON", ""
    ).strip():
        os.environ["AILS_PRIVATE_MIGRATIONS_JSON"] = load_private_payload_from_sheet(
            migration_id
        )
    return run_migration(migration_id, apply=apply)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    errors = run_request(args.request)
    if errors:
        raise SystemExit("migration request failed: " + ",".join(errors))


if __name__ == "__main__":
    main()
