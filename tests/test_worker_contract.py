from ails_intel.worker_contract import (
    collector_diagnostics,
    make_candidate_id,
    next_attempt_id,
    validate_candidate,
    validate_shadow_worker_snapshot,
)

RUN_KEY = "AILS11S-20260809-2030-BJT"
ATTEMPT = f"{RUN_KEY}-A1"


def candidate(**overrides):
    row = {
        "candidate_id": make_candidate_id(RUN_KEY, ATTEMPT, "subject|paper_released|asset|paper_released|v1"),
        "run_key": RUN_KEY,
        "attempt_id": ATTEMPT,
        "source_signal_ids": "SIG-20260809-abc",
        "event_key_v11": "subject|paper_released|asset",
        "delta_key": "subject|paper_released|asset|paper_released|v1",
        "priority_class": "P2",
        "disposition": "selected",
        "schema_version": "v11.0",
    }
    row.update(overrides)
    return row


def test_next_attempt_id_accepts_full_and_legacy_attempts():
    assert next_attempt_id(RUN_KEY, ["A1", f"{RUN_KEY}-A2"]) == f"{RUN_KEY}-A3"


def test_candidate_id_is_deterministic():
    delta = "subject|trial_started|asset|clinical_started|phase2"
    assert make_candidate_id(RUN_KEY, ATTEMPT, delta) == make_candidate_id(RUN_KEY, ATTEMPT, delta)


def test_pending_candidate_requires_complete_watch_fields():
    errors = validate_candidate(candidate(disposition="pending", priority_class="P2"))
    assert "pending_requires_p0_or_p1" in errors
    assert "pending_missing:missing_evidence" in errors


def test_collector_diagnostics_separate_failure_and_saturation():
    result = collector_diagnostics([
        {"execution_status": "partial", "saturation_status": "saturated"},
        {"execution_status": "complete", "saturation_status": "clear"},
    ])
    assert result == {"collector_failure_count": 0, "collector_saturation_count": 1}


def test_shadow_snapshot_passes_candidate_only_boundary():
    errors = validate_shadow_worker_snapshot(
        run_key=RUN_KEY,
        attempt_id=ATTEMPT,
        active_signals=[{"signal_id": "SIG-20260809-abc", "signal_state": "active"}],
        candidates=[candidate()],
        run_rows=[{
            "run_key": RUN_KEY,
            "attempt_id": ATTEMPT,
            "state_status": "verified",
            "delivery_status": "not_started",
            "canonical_attempt": "",
            "candidate_count": 1,
            "schema_version": "v11.0",
        }],
        daily_items=[],
        event_index_rows=[],
    )
    assert errors == []


def test_shadow_snapshot_rejects_downstream_write_and_bad_reference():
    errors = validate_shadow_worker_snapshot(
        run_key=RUN_KEY,
        attempt_id=ATTEMPT,
        active_signals=[{"signal_id": "SIG-20260809-other", "signal_state": "active"}],
        candidates=[candidate()],
        run_rows=[{
            "run_key": RUN_KEY,
            "attempt_id": ATTEMPT,
            "state_status": "verified",
            "delivery_status": "not_started",
            "canonical_attempt": "",
            "candidate_count": 1,
            "schema_version": "v11.0",
        }],
        daily_items=[{"run_key": RUN_KEY}],
        event_index_rows=[],
    )
    assert "candidate_references_nonactive_signal" in errors
    assert "sprint3a_dailyitems_write_forbidden" in errors
