from __future__ import annotations

import os
import google.auth
from googleapiclient.discovery import build

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEETS_READONLY_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def spreadsheet_id_from_env() -> str:
    value = os.environ.get("AILS_SPREADSHEET_ID", "").strip()
    if not value:
        raise RuntimeError("AILS_SPREADSHEET_ID is not configured")
    return value


def _build_sheets_service(scopes):
    credentials, _project_id = google.auth.default(scopes=scopes)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def build_sheets_service():
    """Build a read/write Sheets API client from Application Default Credentials (ADC)."""
    return _build_sheets_service(SHEETS_SCOPES)


def build_sheets_readonly_service():
    """Build a read-only Sheets API client for diagnostic and validation workflows."""
    return _build_sheets_service(SHEETS_READONLY_SCOPES)
