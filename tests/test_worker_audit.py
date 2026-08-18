from ails_intel.worker_audit import validate_worker_audit_snapshot

RUN = "AILS11S-20260818-2030-BJT"
ATTEMPT = RUN + "-A1"
ROUTE = "worker/c1/broad/01"
REQUIRED = {"C1": {ROUTE}}


def _summary(**overrides):
    row = {
        "audit_id": "sha256:summary",
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "source_id": "",
        "row_type": "route_summary",
        "query_ref_type": "broad_slot",
        "query_ref_id": "1",
        "execution_status": "complete",
        "results_returned": "3",
        "results_screened": "1",
        "pages_opened": "1",
        "fresh_results": "1",
        "qualifying_results": "1",
        "schema_version": "v11.1",
    }
    row.update(overrides)
    return row


def _result(**overrides):
    row = {
        "audit_id": "sha256:result",
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "row_type": "result",
        "result_rank": "1",
        "result_title": "Fresh AI healthcare event",
        "result_url": "https://example.com/event",
        "result_source": "Example",
        "published_at": "2026-08-18",
        "opened": "TRUE",
        "disposition": "qualified_signal",
        "reject_reason": "",
        "signal_id": "SIG-20260818-example",
        "schema_version": "v11.1",
    }
    row.update(overrides)
    return row


def _coverage(**overrides):
    row = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "execution_status": "complete",
        "results_seen": "1",
        "relevant_signal_count": "1",
    }
    row.update(overrides)
    return row


def _signal(**overrides):
    row = {
        "signal_id": "SIG-20260818-example",
        "run_key": RUN,
        "origin_attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "signal_state": "active",
    }
    row.update(overrides)
    return row


def _validate(audit_rows, coverage_rows=None, signals=None):
    return validate_worker_audit_snapshot(
        run_key=RUN,
        attempt_id=ATTEMPT,
        audit_rows=audit_rows,
        coverage_rows=[_coverage()] if coverage_rows is None else coverage_rows,
        active_signals=[_signal()] if signals is None else signals,
        required_routes=REQUIRED,
        max_result_rows_per_route=5,
    )


def test_worker_audit_happy_path_reconciles_three_ledgers():
    assert _validate([_summary(), _result()]) == []


def test_worker_audit_true_zero_is_numeric_and_has_no_result_rows():
    summary = _summary(
        results_returned="0",
        results_screened="0",
        pages_opened="0",
        fresh_results="0",
        qualifying_results="0",
    )
    coverage = _coverage(results_seen="0", relevant_signal_count="0")
    assert _validate([summary], [coverage], []) == []


def test_worker_audit_rejects_unresolved_attribution_placeholder():
    errors = _validate([_summary(results_returned="UNRESOLVED_ATTRIBUTION"), _result()])
    assert "worker_audit_noninteger:results_returned" in errors


def test_worker_audit_never_coerces_attribution_degradation_to_zero():
    summary = _summary(
        execution_status="partial",
        results_returned="0",
        results_screened="1",
    )
    errors = _validate([summary, _result()])
    assert "worker_audit_screened_exceeds_returned" in errors


def test_worker_audit_rejects_coverage_results_seen_mismatch():
    errors = _validate([_summary(), _result()], [_coverage(results_seen="0")])
    assert "worker_audit_results_seen_mismatch" in errors


def test_worker_audit_rejects_missing_qualifying_signal():
    errors = _validate([_summary(), _result()], [_coverage()], [])
    assert "worker_audit_qualifying_signal_count_mismatch" in errors
    assert "worker_audit_result_signal_unresolved" in errors


def test_worker_audit_rejects_duplicate_route_summary_and_audit_id():
    duplicate = _summary()
    errors = _validate([_summary(), duplicate, _result()])
    assert "worker_audit_id_duplicate" in errors
    assert "worker_audit_route_summary_duplicate:C1" in errors
