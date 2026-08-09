from __future__ import annotations

import os
import google.auth
from googleapiclient.discovery import build

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def spreadsheet_id_from_env() -> str:
    value = os.environ.get("AILS_SPREADSHEET_ID", "").strip()
    if not value:
        raise RuntimeError("AILS_SPREADSHEET_ID is not configured")
    return value


def build_sheets_service():
    """Build a Sheets API client from Application Default Credentials (ADC)."""
    credentials, _project_id = google.auth.default(scopes=SHEETS_SCOPES)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)
