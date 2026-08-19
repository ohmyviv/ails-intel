from copy import deepcopy

from ails_intel.fingerprint import frozen_manifest_fingerprint
from ails_intel.frozen_shadow_acceptance import project_frozen_structured_for_shadow_acceptance
from ails_intel.shadow_acceptance import evaluate_shadow_acceptance
from ails_intel.signal_keys import make_coverage_id
from ails_intel.unified_ingestion import structured_snapshot_fingerprint

RUN = "AILS11M-20260818-0744-BJT"
ATTEMPT = RUN + "-A3"
SOURCE_RUN = "AILS11S-20260818-2030-BJT"
SOURCE_ATTEMPT = SOURCE_RUN + "-A1"
ROUTE = "worker/plan/E6"


def _source_rows():
    signal = {
        "signal_id": "SIG-S1",
        "run_key": SOURCE_RUN,
        "origin_attempt_id": SOURCE_ATTEMPT,
        "producer_id": "collector/COL-A",
        "channel_id": "C3",
        "route_id": "collector/COL-A",
        "source_id": "SRC-A",
        "signal_state": "active",
        "raw_title": "Structured discovery",
        "url": "https://example.org/structured",
        "schema_version": "v11.0",
    }
    coverage = {
        "run_key": SOURCE_RUN,
        "attempt_id": SOURCE_ATTEMPT,
        "producer_id": "collector/COL-A",
        "channel_id": "C3",
        "route_id": "collector/COL-A",
        "source_id": "SRC-A",
        "execution_status": "complete",
        "checked_at_bjt": "2026-08-18T20:31:00+08:00",
        "relevant_signal_count": "1",
    }
    fingerprint = structured_snapshot_fingerprint(
        run_key=SOURCE_RUN,
        attempt_id=SOURCE_ATTEMPT,
        active_signals=[signal],
        coverage_rows=[coverage],
    )
    return signal, coverage, fingerprint


def _current_worker_coverage():
    return {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "source_id": "",
        "coverage_id": make_coverage_id(RUN, "chatgpt/worker", ATTEMPT, "C1", ROUTE, ""),
        "execution_status": "complete",
        "results_seen": "0",
        "relevant_signal_count": "0",
    }


def test_projection_is_read_only_and_moves_structured_rows_in_memory_only():
    signal, coverage, fingerprint = _source_rows()
    original_signal = deepcopy(signal)
    original_coverage = deepcopy(coverage)
    result = project_frozen_structured_for_shadow_acceptance(
        run_key=RUN,
        source_run_key=SOURCE_RUN,
        source_attempt_id=SOURCE_ATTEMPT,
        qualified_source_signals=[signal],
        qualified_source_coverage=[coverage],
        expected_qualified_fingerprint=fingerprint,
        current_active_signals=[],
        current_coverage_rows=[_current_worker_coverage()],
    )
    assert result.errors == ()
    assert result.source_signal_count == 1
    assert result.source_coverage_count == 1
    assert result.active_signals[0]["run_key"] == RUN
    assert any(row["producer_id"] == "collector/COL-A" and row["run_key"] == RUN for row in result.coverage_rows)
    assert signal == original_signal
    assert coverage == original_coverage


def test_projection_fails_closed_on_fingerprint_drift():
    signal, coverage, _ = _source_rows()
    result = project_frozen_structured_for_shadow_acceptance(
        run_key=RUN,
        source_run_key=SOURCE_RUN,
        source_attempt_id=SOURCE_ATTEMPT,
        qualified_source_signals=[signal],
        qualified_source_coverage=[coverage],
        expected_qualified_fingerprint="sha256:wrong",
        current_active_signals=[],
        current_coverage_rows=[_current_worker_coverage()],
    )
    assert "frozen_acceptance_qualified_fingerprint_mismatch" in result.errors


def test_projection_rejects_mixed_manual_structured_rows():
    signal, coverage, fingerprint = _source_rows()
    manual_collector = dict(signal)
    manual_collector["run_key"] = RUN
    result = project_frozen_structured_for_shadow_acceptance(
        run_key=RUN,
        source_run_key=SOURCE_RUN,
        source_attempt_id=SOURCE_ATTEMPT,
        qualified_source_signals=[signal],
        qualified_source_coverage=[coverage],
        expected_qualified_fingerprint=fingerprint,
        current_active_signals=[manual_collector],
        current_coverage_rows=[_current_worker_coverage()],
    )
    assert result.errors == ("frozen_acceptance_manual_structured_signals_present",)


def test_projected_frozen_source_satisfies_existing_final_ledger_contract():
    signal, coverage, fingerprint = _source_rows()
    worker_coverage = _current_worker_coverage()
    projection = project_frozen_structured_for_shadow_acceptance(
        run_key=RUN,
        source_run_key=SOURCE_RUN,
        source_attempt_id=SOURCE_ATTEMPT,
        qualified_source_signals=[signal],
        qualified_source_coverage=[coverage],
        expected_qualified_fingerprint=fingerprint,
        current_active_signals=[],
        current_coverage_rows=[worker_coverage],
    )
    assert projection.errors == ()

    candidate = {
        "candidate_id": "CAN-1",
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "source_signal_ids": "SIG-S1",
        "event_key_v11": "EV-1",
        "delta_key": "DELTA-1",
        "disposition": "selected",
    }
    item = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "item_index": "1",
        "title": "Structured discovery",
        "primary_url": "https://example.org/structured",
        "event_key_v11": "EV-1",
        "delta_key": "DELTA-1",
    }
    run = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "report_date": "2026-08-18",
        "completed_at_bjt": "2026-08-19T11:30:00+08:00",
        "stage": "completed",
        "final_status": "shadow_passed",
        "state_status": "passed",
        "delivery_status": "delivered",
        "resume_stage": "passed",
        "canonical_attempt": "",
        "transaction_id": ATTEMPT,
        "schema_version": "v11.0",
        "readback_match": "TRUE",
        "write_status": "success",
        "readback_status": "passed",
        "candidate_count": "1",
        "verified_count": "1",
        "selected_count": "1",
        "frozen_item_count": "1",
        "frozen_content_fingerprint": frozen_manifest_fingerprint([item]),
        "coverage_confidence_pre_rescue": "MEDIUM",
        "coverage_confidence": "MEDIUM",
        "rescue_triggered": "FALSE",
        "signal_count": "1",
        "channel_health_json": '{"C1":"complete"}',
    }
    audits = [
        {
            "audit_id": "AUD-SUMMARY",
            "run_key": RUN,
            "attempt_id": ATTEMPT,
            "producer_id": "chatgpt/worker",
            "channel_id": "C1",
            "route_id": ROUTE,
            "row_type": "route_summary",
            "results_screened": "0",
            "qualifying_results": "0",
        }
    ]
    cfg = {
        "structured_collectors_json": [{"id": "COL-A", "enabled": True}],
        "collector_snapshot_not_before_bjt": "18:00:00",
        "worker_route_audit_max_result_rows_per_route": 5,
        "max_items": 12,
    }

    result = evaluate_shadow_acceptance(
        report_date="2026-08-18",
        run_key=RUN,
        attempt_id=ATTEMPT,
        cfg=cfg,
        run_rows=[run],
        active_signals=projection.active_signals,
        candidates=[candidate],
        coverage_rows=projection.coverage_rows,
        worker_audit_rows=audits,
        daily_items=[item],
        event_index_rows=[],
        required_routes={"C1": {ROUTE}},
        enforce_continuation=True,
    )
    assert result.ledger_verdict == "PASS"
    assert result.errors == ()
    assert result.metrics["structured_signal_count"] == 1
    assert result.metrics["worker_or_rescue_coverage_count"] == 1
