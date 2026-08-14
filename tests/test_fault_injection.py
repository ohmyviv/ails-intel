from types import SimpleNamespace

import pytest

from ails_intel import collector_runner
from ails_intel.coverage_gate import validate_gate_snapshot
from ails_intel.fingerprint import frozen_manifest_fingerprint
from ails_intel.freeze_contract import validate_shadow_freeze_snapshot
from ails_intel.snapshot_policy import (
    barrier_required_structured_collector_ids,
    validate_structured_snapshot_barrier,
)


class _CfgValue:
    def __init__(self, value):
        self.value = value


class _FakeStore:
    def __init__(self):
        self.coverage = []
        self.signals = []

    def signal_key_records(self, run_key):
        return {}

    def latest_source_signals(self, source_id, exclude_run_key=None):
        return {}

    def reactivate_diagnostic_signals(self, updates):
        return None

    def append_signals(self, signals):
        self.signals.extend(signals)

    def upsert_coverage(self, coverage):
        self.coverage.extend(coverage)


class _FailingCollector:
    def collect(self, **kwargs):
        raise TimeoutError("injected source timeout")


class _HealthyCollector:
    def collect(self, **kwargs):
        return SimpleNamespace(
            relevant_items=[],
            representative_url="https://example.org/healthy",
            execution_status="complete",
            failure_reason="",
            diagnostic_note="",
            saturation_status="not_saturated",
            results_seen=3,
        )


def test_single_source_timeout_degrades_batch_but_does_not_stop_remaining_collectors(monkeypatch):
    """Fault injection: one source times out, the batch continues and exits successfully."""
    store = _FakeStore()
    specs = [
        SimpleNamespace(
            collector_id="COL-BIORXIV",
            source_id="SRC-BIORXIV",
            channel_id="C5",
            options={},
        ),
        SimpleNamespace(
            collector_id="COL-PUBMED",
            source_id="SRC-PUBMED",
            channel_id="C5",
            options={},
        ),
    ]
    sources = {
        "SRC-BIORXIV": SimpleNamespace(source_name="bioRxiv"),
        "SRC-PUBMED": SimpleNamespace(source_name="PubMed"),
    }
    cfg = {
        "execution_mode": _CfgValue("shadow"),
        "collector_write_signals_enabled": _CfgValue(True),
        "timezone": _CfgValue("Asia/Shanghai"),
        "collector_limits_json": _CfgValue({}),
        "collector_timeout_seconds": _CfgValue(1),
        "collector_retry_limit": _CfgValue(0),
        "collector_default_max_results": _CfgValue(10),
    }

    monkeypatch.setattr(collector_runner, "build_sheets_service", lambda: object())
    monkeypatch.setattr(collector_runner, "spreadsheet_id_from_env", lambda: "test-sheet")
    monkeypatch.setattr(collector_runner, "SheetsStore", lambda service, spreadsheet_id: store)
    monkeypatch.setattr(collector_runner, "load_active_config", lambda store: cfg)
    monkeypatch.setattr(collector_runner, "build_run_key", lambda cfg, now: "AILS11S-FI")
    monkeypatch.setattr(collector_runner, "collector_specs", lambda cfg: specs)
    monkeypatch.setattr(collector_runner, "load_source_specs", lambda store, ids: sources)
    monkeypatch.setattr(collector_runner, "collector_window_days", lambda cfg, channel_id: 2)
    monkeypatch.setattr(collector_runner, "HttpClient", lambda timeout, retries: object())
    monkeypatch.setattr(collector_runner, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        collector_runner,
        "_build_collector",
        lambda spec, prior_signals=None: _FailingCollector()
        if spec.collector_id == "COL-BIORXIV"
        else _HealthyCollector(),
    )
    monkeypatch.setattr("sys.argv", ["collector_runner"])

    with pytest.raises(SystemExit) as exc:
        collector_runner.main()

    assert exc.value.code == 0
    assert len(store.coverage) == 2
    assert store.coverage[0].values["source_id"] == "SRC-BIORXIV"
    assert store.coverage[0].values["execution_status"] == "failed"
    assert store.coverage[0].values["failure_reason"] == "TimeoutError"
    assert store.coverage[1].values["source_id"] == "SRC-PUBMED"
    assert store.coverage[1].values["execution_status"] == "complete"


def test_single_source_failure_is_terminal_observation_and_low_coverage_can_reach_freeze():
    """Contract-level continuation across barrier, coverage gate, and freeze."""
    cfg = {
        "structured_collectors_json": [
            {"id": "COL-BIORXIV", "enabled": True, "barrier_required": True},
            {"id": "COL-PUBMED", "enabled": True, "barrier_required": True},
        ]
    }
    expected = barrier_required_structured_collector_ids(cfg)
    assert expected == {"COL-BIORXIV", "COL-PUBMED"}

    coverage = [
        {
            "run_key": "AILS11S-FI",
            "producer_id": "collector/COL-BIORXIV",
            "checked_at_bjt": "2026-08-14T20:33:10+08:00",
            "execution_status": "failed",
        },
        {
            "run_key": "AILS11S-FI",
            "producer_id": "collector/COL-PUBMED",
            "checked_at_bjt": "2026-08-14T20:33:11+08:00",
            "execution_status": "complete",
        },
    ]
    assert validate_structured_snapshot_barrier(
        run_key="AILS11S-FI",
        report_date="2026-08-14",
        coverage_rows=coverage,
        expected_collector_ids=expected,
        not_before_bjt="18:00:00",
    ) == []

    mandatory = ["C1", "C2", "C3", "C4", "C6"]
    run = {
        "stage": "coverage_gate",
        "final_status": "ready_for_freeze",
        "resume_stage": "freeze",
        "state_status": "verified",
        "delivery_status": "not_started",
        "canonical_attempt": "",
        "coverage_confidence_pre_rescue": "LOW",
        "coverage_confidence": "LOW",
        "coverage_gate_reason": "fault injection: one source unavailable after bounded rescue",
        "mandatory_channels_completed": "3",
        "mandatory_channels_total": "5",
        "rescue_triggered": "TRUE",
    }
    channel_health = {
        "C1": "complete",
        "C2": "complete",
        "C3": "complete",
        "C4": "partial",
        "C6": "partial",
    }
    assert validate_gate_snapshot(
        run=run,
        mandatory_channels=mandatory,
        channel_health=channel_health,
        daily_items_for_run=0,
        event_index_ownership_count=0,
    ) == []

    run_key = "AILS11S-FI"
    attempt_id = run_key + "-A1"
    candidate = {
        "run_key": run_key,
        "attempt_id": attempt_id,
        "delta_key": "d-fi",
        "event_key_v11": "e-fi",
        "disposition": "selected",
    }
    item = {
        "run_key": run_key,
        "attempt_id": attempt_id,
        "item_index": 1,
        "title": "Fault injection item",
        "primary_url": "https://example.org/item",
        "event_key_v11": "e-fi",
        "delta_key": "d-fi",
        "schema_version": "v11.0",
    }
    freeze_run = {
        "run_key": run_key,
        "attempt_id": attempt_id,
        "stage": "freeze",
        "state_status": "committed",
        "delivery_status": "not_started",
        "resume_stage": "report",
        "canonical_attempt": "",
        "coverage_confidence": "LOW",
        "frozen_item_count": 1,
        "selected_count": 1,
        "write_status": "success",
        "readback_status": "success",
        "readback_match": "TRUE",
        "frozen_content_fingerprint": frozen_manifest_fingerprint([item]),
    }
    assert validate_shadow_freeze_snapshot(
        run_key=run_key,
        attempt_id=attempt_id,
        candidates=[candidate],
        daily_items=[item],
        run_rows=[freeze_run],
        event_index_rows=[],
        max_items=12,
    ) == []
