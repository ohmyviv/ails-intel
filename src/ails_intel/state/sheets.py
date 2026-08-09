from __future__ import annotations

from ails_intel.models import COVERAGE_HEADERS, CoverageRecord, SignalRecord


class SheetsStore:
    def __init__(self, service, spreadsheet_id: str):
        self.service = service
        self.spreadsheet_id = spreadsheet_id

    def rows(self, a1_range: str) -> list[list[object]]:
        return (
            self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id, range=a1_range
            ).execute().get("values", [])
        )

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
        """Reactivate only the one-time pre-Sprint-2.1 diagnostic rows.

        The first live shadow run deliberately invalidated all of its rows after
        quality defects were found. A later collector run may prove that some of
        those exact signal keys are still valid under the corrected query logic.
        For those diagnostic rows only, updating W:AA is a controlled migration
        exception: it restores the corrected priority/core hints plus state/notes
        without creating a duplicate deterministic signal_id/signal_key.
        """
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
        self.service.spreadsheets().values().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"valueInputOption": "RAW", "data": data},
        ).execute()
        return len(updates)

    def append_signals(self, signals: list[SignalRecord]) -> int:
        if not signals:
            return 0
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Lite_Signals!A:AB",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [s.row() for s in signals]},
        ).execute()
        return len(signals)

    def upsert_coverage(self, records: list[CoverageRecord]) -> None:
        if not records:
            return
        rows = self.rows("Lite_SourceCoverage!A:X")
        header = rows[0] if rows else COVERAGE_HEADERS
        pos = {h: i for i, h in enumerate(header)}
        if "coverage_id" not in pos:
            raise RuntimeError("Lite_SourceCoverage missing coverage_id")
        existing = {}
        for idx, row in enumerate(rows[1:], start=2):
            row = list(row) + [""] * max(0, len(header) - len(row))
            cid = str(row[pos["coverage_id"]]).strip()
            if cid:
                existing[cid] = idx

        append_rows = []
        data = []
        for rec in records:
            row = rec.row()
            cid = str(rec.values.get("coverage_id", ""))
            if cid in existing:
                data.append({"range": f"Lite_SourceCoverage!A{existing[cid]}:X{existing[cid]}", "values": [row]})
            else:
                append_rows.append(row)

        if data:
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": data},
            ).execute()
        if append_rows:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="Lite_SourceCoverage!A:X",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": append_rows},
            ).execute()
