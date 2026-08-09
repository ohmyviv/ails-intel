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

    def active_signal_keys(self, run_key: str) -> set[str]:
        rows = self.rows("Lite_Signals!A:AB")
        if not rows:
            return set()
        header = rows[0]
        pos = {h: i for i, h in enumerate(header)}
        if "run_key" not in pos or "signal_key" not in pos:
            raise RuntimeError("Lite_Signals headers missing run_key/signal_key")
        out = set()
        for row in rows[1:]:
            row = list(row) + [""] * max(0, len(header) - len(row))
            if str(row[pos["run_key"]]) == run_key:
                key = str(row[pos["signal_key"]]).strip()
                if key:
                    out.add(key)
        return out

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
