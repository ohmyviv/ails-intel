from ails_intel.source_route_integrity import reconcile_due_source_routes


RUN = "AILS11S-20260815-2030-BJT"
ATTEMPT = f"{RUN}-A2"
ROUTE = "worker/source/SRC-EXAMPLE"


def audit(**overrides):
    row = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "source_id": "SRC-EXAMPLE",
        "row_type": "route_summary",
        "execution_status": "complete",
    }
    row.update(overrides)
    return row


def coverage(**overrides):
    row = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "source_id": "SRC-EXAMPLE",
        "execution_status": "complete",
    }
    row.update(overrides)
    return row


def test_due_source_route_reconciles_across_any_worker_channel():
    result = reconcile_due_source_routes(
        run_key=RUN,
        attempt_id=ATTEMPT,
        due_source_route_ids={ROUTE},
        audit_rows=[audit(channel_id="C4")],
        coverage_rows=[coverage(channel_id="C4")],
    )
    assert result.errors == ()
    assert result.required_route_count == 1
    assert result.completed_route_count == 1
    assert result.incomplete_route_count == 0


def test_missing_due_source_route_is_integrity_error():
    result = reconcile_due_source_routes(
        run_key=RUN,
        attempt_id=ATTEMPT,
        due_source_route_ids={ROUTE},
        audit_rows=[],
        coverage_rows=[],
    )
    assert "due_source_audit_missing" in result.errors
    assert "due_source_coverage_missing" in result.errors


def test_incomplete_due_source_is_coverage_degradation_not_integrity_error():
    result = reconcile_due_source_routes(
        run_key=RUN,
        attempt_id=ATTEMPT,
        due_source_route_ids={ROUTE},
        audit_rows=[audit(execution_status="partial")],
        coverage_rows=[coverage(execution_status="partial")],
    )
    assert result.errors == ()
    assert result.completed_route_count == 0
    assert result.incomplete_route_count == 1


def test_due_source_audit_and_coverage_must_agree():
    result = reconcile_due_source_routes(
        run_key=RUN,
        attempt_id=ATTEMPT,
        due_source_route_ids={ROUTE},
        audit_rows=[audit(execution_status="complete")],
        coverage_rows=[coverage(execution_status="partial")],
    )
    assert "due_source_execution_status_mismatch" in result.errors


def test_due_source_identity_is_reconciled_from_route_id():
    result = reconcile_due_source_routes(
        run_key=RUN,
        attempt_id=ATTEMPT,
        due_source_route_ids={ROUTE},
        audit_rows=[audit(source_id="SRC-WRONG")],
        coverage_rows=[coverage()],
    )
    assert "due_source_audit_source_mismatch" in result.errors
