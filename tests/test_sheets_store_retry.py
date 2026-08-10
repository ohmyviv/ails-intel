import ssl

from ails_intel.models import COVERAGE_HEADERS, SIGNAL_HEADERS, CoverageRecord, SignalRecord
from ails_intel.state.sheets import SheetsStore


class FakeRequest:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, num_retries=0):
        return self.fn()


class FakeValues:
    def __init__(self):
        self.signal_rows = []
        self.coverage_rows = []
        self.append_calls = []
        self.fail_signal_append_after_commit_once = False
        self.fail_coverage_append_after_commit_once = False

    def get(self, *, spreadsheetId, range):
        def run():
            if range == "Lite_Signals!A:AB":
                return {"values": [SIGNAL_HEADERS] + self.signal_rows}
            if range == "Lite_SourceCoverage!A:X":
                return {"values": [COVERAGE_HEADERS] + self.coverage_rows}
            raise AssertionError(range)
        return FakeRequest(run)

    def append(self, *, spreadsheetId, range, valueInputOption, insertDataOption, body):
        rows = [list(row) for row in body["values"]]
        self.append_calls.append((range, len(rows)))

        def run():
            if range == "Lite_Signals!A:AB":
                self.signal_rows.extend(rows)
                if self.fail_signal_append_after_commit_once:
                    self.fail_signal_append_after_commit_once = False
                    raise ssl.SSLEOFError(8, "lost response after commit")
                return {}
            if range == "Lite_SourceCoverage!A:X":
                self.coverage_rows.extend(rows)
                if self.fail_coverage_append_after_commit_once:
                    self.fail_coverage_append_after_commit_once = False
                    raise ssl.SSLEOFError(8, "lost response after commit")
                return {}
            raise AssertionError(range)
        return FakeRequest(run)

    def batchUpdate(self, *, spreadsheetId, body):
        return FakeRequest(lambda: {})


class FakeSpreadsheets:
    def __init__(self, values):
        self._values = values

    def values(self):
        return self._values


class FakeService:
    def __init__(self, values):
        self._spreadsheets = FakeSpreadsheets(values)

    def spreadsheets(self):
        return self._spreadsheets


def signal(run_key: str, key: str) -> SignalRecord:
    return SignalRecord({
        "signal_id": f"SIG-{key}",
        "run_key": run_key,
        "signal_key": key,
        "signal_state": "active",
        "schema_version": "v11.0",
    })


def coverage(run_key: str, cid: str) -> CoverageRecord:
    return CoverageRecord({
        "run_key": run_key,
        "coverage_id": cid,
        "execution_status": "complete",
        "schema_version": "v11.0",
    })


def test_signal_appends_are_chunked():
    values = FakeValues()
    store = SheetsStore(FakeService(values), "sheet")
    records = [signal("RUN", f"k{i}") for i in range(41)]
    assert store.append_signals(records) == 41
    assert values.append_calls == [
        ("Lite_Signals!A:AB", 40),
        ("Lite_Signals!A:AB", 1),
    ]
    assert len(values.signal_rows) == 41


def test_signal_append_reconciles_unknown_commit_without_duplicate():
    values = FakeValues()
    values.fail_signal_append_after_commit_once = True
    store = SheetsStore(FakeService(values), "sheet")
    store.append_signals([signal("RUN", "k1")])
    assert len(values.signal_rows) == 1
    assert values.append_calls == [("Lite_Signals!A:AB", 1)]


def test_coverage_append_reconciles_unknown_commit_without_duplicate():
    values = FakeValues()
    values.fail_coverage_append_after_commit_once = True
    store = SheetsStore(FakeService(values), "sheet")
    store.upsert_coverage([coverage("RUN", "c1")])
    assert len(values.coverage_rows) == 1
    assert values.append_calls == [("Lite_SourceCoverage!A:X", 1)]
