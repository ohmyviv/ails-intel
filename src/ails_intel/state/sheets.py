from __future__ import annotations

import socket
import ssl
import time

from google.auth.exceptions import TransportError
from googleapiclient.errors import HttpError

from ails_intel.models import COVERAGE_HEADERS, CoverageRecord, SignalRecord

SIGNAL_APPEND_CHUNK_SIZE = 40
COVERAGE_APPEND_CHUNK_SIZE = 40
WRITE_RETRY_LIMIT = 3
RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}


def _chunks(values, size: int):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _is_retryable_write_error(exc: Exception) -> bool:
    if isinstance(exc, (ssl.SSLError, socket.timeout, TimeoutError, ConnectionError, TransportError)):
        return True
    if isinstance(exc, HttpError):
        status = int(getattr(exc.resp, "status", 0) or 0)
        return status in RETRYABLE_HTTP_STATUS
    return False


class SheetsStore:
    def __init__(self, service, spreadsheet_id: str):
        self.service = service
        self.spreadsheet_id = spreadsheet_id

    def _read_execute(self, request):
        # Reads and deterministic range updates are safe for client retries.
        return request.execute(num_retries=WRITE_RETRY_LIMIT)

    def rows(self, a1_range: str) -> list[list[object]]:
        return self._read_execute(
            self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id, range=a1_range
            )
        ).get("values", [])

    def dict_rows(self, a1_range: str) -> list[dict[str, object]]:
        """Return Sheet rows keyed by their live header without logging content."""
        rows = self.rows(a1_range)
        if not rows:
            return []
        header = [str(x).strip() for x in rows[0]]
        out: list[dict[str, object]] = []
        for raw in rows[1:]:
            row = list(raw) + [""] * max(0, len(header) - len(raw))
            out.append({header[i]: row[i] for i in range(len(header))})
        return out

    def active_signals(self, run_key: str) -> list[dict[str, object]]:
        return [
            row
            for row in self.dict_rows("Lite_Signals!A:AB")
            if str(row.get("run_key", "")).strip() == run_key
            and str(row.get("signal_state", "")).strip() == "active"
        ]

    def latest_source_signals(self, source_id: str, *, exclude_run_key: str = "") -> dict[str, dict[str, object]]:
        """Return the latest persisted Signal row for each stable_id of a source.

        This is intentionally a read-only historical view used by deterministic
        source adapters that need to distinguish a material state change from a
        registry/article record merely appearing in today's update window.
        """
        out: dict[str, dict[str, object]] = {}
        for row in self.dict_rows("Lite_Signals!A:AB"):
            if str(row.get("source_id", "")).strip() != source_id:
                continue
            if exclude_run_key and str(row.get("run_key", "")).strip() == exclude_run_key:
                continue
            stable_id = str(row.get("stable_id", "")).strip()
            if stable_id:
                out[stable_id] = row
        return out

    def coverage_rows(self, run_key: str) -> list[dict[str, object]]:
        return [
            row
            for row in self.dict_rows("Lite_SourceCoverage!A:X")
            if str(row.get("run_key", "")).strip() == run_key
        ]

    def candidate_rows(self, run_key: str, attempt_id: str = "") -> list[dict[str, object]]:
        rows = [
            row
            for row in self.dict_rows("Lite_Candidates!A:AK")
            if str(row.get("run_key", "")).strip() == run_key
        ]
        if attempt_id:
            rows = [row for row in rows if str(row.get("attempt_id", "")).strip() == attempt_id]
        return rows

    def run_rows(self, run_key: str, attempt_id: str = "") -> list[dict[str, object]]:
        rows = [
            row
            for row in self.dict_rows("Lite_Runs!A:BN")
            if str(row.get("run_key", "")).strip() == run_key
        ]
        if attempt_id:
            rows = [row for row in rows if str(row.get("attempt_id", "")).strip() == attempt_id]
        return rows

    def daily_item_rows(self, run_key: str) -> list[dict[str, object]]:
        return [
            row
            for row in self.dict_rows("Lite_DailyItems!A:AD")
            if str(row.get("run_key", "")).strip() == run_key
        ]

    def event_index_rows(self) -> list[dict[str, object]]:
        return self.dict_rows("Lite_EventIndex!A:AA")

    def signal_key_records(self, run_key: str) -> dict[str, dict[str, object]]:
        rows = self.rows("Lite_Signals!A:AB")
        if not rows:
            return {}
        header = rows[0]
        pos = {h: i for i, h in enumerate(header)}
        required = {"run_key", "signal_key", "signal_state", "notes"}
        missing = required - set(pos)
        if missing:
            raise RuntimeError(f"Lite_Signals headers missing: {sorted(missing)}")

        out: dict[str, dict[str, object]] = {}
        for idx, row in enumerate(rows[1:], start=2):
            row = list(row) + [""] * max(0, len(header) - len(row))
            if str(row[pos["run_key"]]).strip() != run_key:
                continue
            key = str(row[pos["signal_key"]]).strip()
            if not key:
                continue
            out[key] = {
                "row": idx,
                "state": str(row[pos["signal_state"]]).strip(),
                "notes": str(row[pos["notes"]]).strip(),
            }
        return out

    def active_signal_keys(self, run_key: str) -> set[str]:
        return {
            key
            for key, rec in self.signal_key_records(run_key).items()
            if str(rec.get("state", "")).strip() == "active"
        }

    def reactivate_diagnostic_signals(self, updates: list[tuple[int, str]]) -> int:
        """Reactivate only the one-time pre-Sprint-2.1 diagnostic rows."""
        if not updates:
            return 0
        data = []
        for row_idx, priority in updates:
            data.append(
                {
                    "range": f"Lite_Signals!W{row_idx}:AA{row_idx}",
                    "values": [[priority, "TRUE", "TRUE", "active", "revalidated_after_sprint2.1"]],
                }
            )
        self._read_execute(
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": data},
            )
        )
        return len(updates)

    def _append_signal_chunk(self, chunk: list[SignalRecord]) -> None:
        pending = list(chunk)
        run_keys = {str(signal.values.get("run_key", "")).strip() for signal in pending}
        if len(run_keys) != 1 or not next(iter(run_keys), ""):
            raise RuntimeError("signal append chunk must contain exactly one non-empty run_key")
        run_key = next(iter(run_keys))

        for attempt in range(WRITE_RETRY_LIMIT + 1):
            try:
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range="Lite_Signals!A:AB",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [signal.row() for signal in pending]},
                ).execute(num_retries=0)
                return
            except Exception as exc:
                if not _is_retryable_write_error(exc) or attempt >= WRITE_RETRY_LIMIT:
                    raise
                # Append is not safely retryable if the server may have committed
                # before the connection died. Re-read deterministic signal keys and
                # retry only the rows that are still absent.
                time.sleep(min(2 ** attempt, 4))
                existing = self.signal_key_records(run_key)
                pending = [
                    signal for signal in pending
                    if str(signal.values.get("signal_key", "")).strip() not in existing
                ]
                if not pending:
                    return

    def append_signals(self, signals: list[SignalRecord]) -> int:
        if not signals:
            return 0
        for chunk in _chunks(signals, SIGNAL_APPEND_CHUNK_SIZE):
            self._append_signal_chunk(chunk)
        return len(signals)

    def _coverage_index(self) -> dict[str, int]:
        rows = self.rows("Lite_SourceCoverage!A:X")
        if not rows:
            return {}
        header = rows[0]
        pos = {h: i for i, h in enumerate(header)}
        if "coverage_id" not in pos:
            raise RuntimeError("Lite_SourceCoverage missing coverage_id")
        existing: dict[str, int] = {}
        for idx, row in enumerate(rows[1:], start=2):
            row = list(row) + [""] * max(0, len(header) - len(row))
            cid = str(row[pos["coverage_id"]]).strip()
            if cid:
                existing[cid] = idx
        return existing

    def _append_coverage_chunk(self, chunk: list[CoverageRecord]) -> None:
        pending = list(chunk)
        for attempt in range(WRITE_RETRY_LIMIT + 1):
            try:
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range="Lite_SourceCoverage!A:X",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [record.row() for record in pending]},
                ).execute(num_retries=0)
                return
            except Exception as exc:
                if not _is_retryable_write_error(exc) or attempt >= WRITE_RETRY_LIMIT:
                    raise
                time.sleep(min(2 ** attempt, 4))
                existing = self._coverage_index()
                pending = [
                    record for record in pending
                    if str(record.values.get("coverage_id", "")).strip() not in existing
                ]
                if not pending:
                    return

    def upsert_coverage(self, records: list[CoverageRecord]) -> None:
        if not records:
            return
        existing = self._coverage_index()
        append_records: list[CoverageRecord] = []
        update_data = []
        for rec in records:
            row = rec.row()
            cid = str(rec.values.get("coverage_id", "")).strip()
            if cid in existing:
                update_data.append({"range": f"Lite_SourceCoverage!A{existing[cid]}:X{existing[cid]}", "values": [row]})
            else:
                append_records.append(rec)

        for data_chunk in _chunks(update_data, COVERAGE_APPEND_CHUNK_SIZE):
            self._read_execute(
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"valueInputOption": "RAW", "data": data_chunk},
                )
            )
        for record_chunk in _chunks(append_records, COVERAGE_APPEND_CHUNK_SIZE):
            self._append_coverage_chunk(record_chunk)
