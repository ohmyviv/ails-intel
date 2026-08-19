import copy

from ails_intel.worker_execution_journal import (
    DurableExecutionJournal,
    derive_route_summary,
    load_jsonl,
    materialize_route_result_rows,
    materialize_route_summary,
    validate_result_rows_against_events,
    validate_summary_against_events,
    validate_worker_execution_journal,
)

RUN = "AILS11M-20260818-0744-BJT"
ATTEMPT = RUN + "-A3"
ROUTE = "worker/plan/V9-CN10"
CHANNEL = "C6"


def _append(writer, event_type, **payload):
    return writer.append_and_verify(
        {
            "run_key": RUN,
            "attempt_id": ATTEMPT,
            "channel_id": CHANNEL,
            "route_id": ROUTE,
            "event_type": event_type,
            **payload,
        }
    )


def _screened_payload(rank, *, fresh=False, disposition="rejected", reject_reason="outside_window", signal_id=""):
    payload = {
        "result_rank": rank,
        "result_title": f"Result {rank}",
        "result_url": f"https://example.com/{rank}",
        "result_source": "Example",
        "published_at": "2026-08-18" if fresh else "2026-08-01",
        "fresh": fresh,
        "disposition": disposition,
    }
    if disposition == "rejected":
        payload["reject_reason"] = reject_reason
    else:
        payload["signal_id"] = signal_id or f"SIG-{rank}"
    return payload


def _happy_events(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=6)
    _append(writer, "page_opened", result_rank=1, success=True, url="https://example.com/1")
    _append(writer, "page_opened", result_rank=2, success=True, url="https://example.com/2")
    _append(writer, "result_screened", **_screened_payload(1, fresh=True, disposition="qualified_signal", signal_id="SIG-1"))
    _append(writer, "result_screened", **_screened_payload(2, fresh=False, reject_reason="outside_window"))
    _append(writer, "route_finalized", execution_status="complete")
    _append(writer, "route_sealed")
    return load_jsonl(writer.path)


def test_happy_path_derives_execution_facts(tmp_path):
    events = _happy_events(tmp_path)
    assert validate_worker_execution_journal(events, required_routes={CHANNEL: {ROUTE}}) == []
    assert derive_route_summary(events) == {
        "channel_id": CHANNEL,
        "route_id": ROUTE,
        "execution_status": "complete",
        "results_returned": 6,
        "results_screened": 2,
        "pages_opened": 2,
        "fresh_results": 1,
        "qualifying_results": 1,
    }


def test_pages_opened_cannot_be_rewritten_from_memory(tmp_path):
    events = _happy_events(tmp_path)
    summary = materialize_route_summary(events, base_fields={"run_key": RUN, "attempt_id": ATTEMPT})
    summary["pages_opened"] = 0
    assert "execution_fact_mismatch:pages_opened" in validate_summary_against_events(summary, events)


def test_open_before_search_journal_fails(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "page_opened", result_rank=1, success=True, url="https://example.com/1")
    _append(writer, "search_returned", results_returned=1)
    _append(writer, "result_screened", **_screened_payload(1, reject_reason="duplicate"))
    _append(writer, "route_finalized", execution_status="complete")
    _append(writer, "route_sealed")
    errors = validate_worker_execution_journal(load_jsonl(writer.path))
    assert "execution_event_order_violation:page_open_before_search_journal" in errors


def test_next_route_cannot_start_before_previous_route_sealed(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = DurableExecutionJournal(path)
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=0)
    writer.append_and_verify(
        {
            "run_key": RUN,
            "attempt_id": ATTEMPT,
            "channel_id": "C1",
            "route_id": "worker/c1/broad/01",
            "event_type": "route_started",
        }
    )
    errors = validate_worker_execution_journal(load_jsonl(path))
    assert "execution_journal_route_interleaving" in errors


def test_true_zero_is_derived_not_declared(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=0)
    _append(writer, "route_finalized", execution_status="complete")
    _append(writer, "route_sealed")
    events = load_jsonl(writer.path)
    assert validate_worker_execution_journal(events) == []
    summary = derive_route_summary(events)
    assert [summary[field] for field in ("results_returned", "results_screened", "pages_opened", "fresh_results", "qualifying_results")] == [0, 0, 0, 0, 0]


def test_failed_search_is_not_complete_true_zero(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_failed", failure_reason="robots_txt")
    _append(writer, "route_finalized", execution_status="failed", failure_reason="robots_txt")
    _append(writer, "route_sealed")
    events = load_jsonl(writer.path)
    assert validate_worker_execution_journal(events) == []
    summary = derive_route_summary(events)
    assert summary["execution_status"] == "failed"
    assert summary["results_returned"] == 0
    assert summary["failure_reason"] == "robots_txt"


def test_ent001_exact_one_is_preserved(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    route = "worker/entity/ENT-001"
    writer.append_and_verify({"run_key": RUN, "attempt_id": ATTEMPT, "channel_id": "C2", "route_id": route, "event_type": "route_started"})
    writer.append_and_verify({"run_key": RUN, "attempt_id": ATTEMPT, "channel_id": "C2", "route_id": route, "event_type": "search_returned", "results_returned": 1})
    writer.append_and_verify({"run_key": RUN, "attempt_id": ATTEMPT, "channel_id": "C2", "route_id": route, "event_type": "result_screened", **_screened_payload(1, reject_reason="old_event_no_delta")})
    writer.append_and_verify({"run_key": RUN, "attempt_id": ATTEMPT, "channel_id": "C2", "route_id": route, "event_type": "route_finalized", "execution_status": "complete"})
    writer.append_and_verify({"run_key": RUN, "attempt_id": ATTEMPT, "channel_id": "C2", "route_id": route, "event_type": "route_sealed"})
    events = load_jsonl(writer.path)
    assert validate_worker_execution_journal(events) == []
    summary = derive_route_summary(events)
    assert summary["results_returned"] == 1
    assert summary["results_screened"] == 1
    assert summary["pages_opened"] == 0
    assert summary["fresh_results"] == 0
    assert summary["qualifying_results"] == 0


def test_route_finalized_rejects_manual_counts(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=1)
    _append(writer, "route_finalized", execution_status="complete", pages_opened=0)
    _append(writer, "route_sealed")
    assert "execution_journal_manual_count_in_finalized_event" in validate_worker_execution_journal(load_jsonl(writer.path))


def test_hash_chain_tampering_is_detected(tmp_path):
    events = _happy_events(tmp_path)
    tampered = copy.deepcopy(events)
    tampered[2]["url"] = "https://evil.example/tampered"
    assert "execution_journal_hash_mismatch" in validate_worker_execution_journal(tampered)


def test_base_fields_cannot_override_execution_facts(tmp_path):
    events = _happy_events(tmp_path)
    try:
        materialize_route_summary(events, base_fields={"pages_opened": 0})
    except ValueError as exc:
        assert str(exc) == "base_fields_must_not_override_execution_facts"
    else:
        raise AssertionError("expected ValueError")


def test_materialization_requires_sealed_route(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=0)
    _append(writer, "route_finalized", execution_status="complete")
    events = load_jsonl(writer.path)
    try:
        materialize_route_summary(events)
    except ValueError as exc:
        assert str(exc) == "route_sealed_count_not_one"
    else:
        raise AssertionError("expected ValueError")


def test_result_screened_missing_identity_metadata_fails_g2(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=1)
    _append(writer, "result_screened", result_rank=1, fresh=False, disposition="rejected", reject_reason="old")
    _append(writer, "route_finalized", execution_status="complete")
    _append(writer, "route_sealed")
    errors = validate_worker_execution_journal(load_jsonl(writer.path))
    assert "execution_journal_result_title_missing" in errors
    assert "execution_journal_result_url_missing" in errors
    assert "execution_journal_result_source_missing" in errors


def test_qualified_result_requires_signal_id(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=1)
    payload = _screened_payload(1, fresh=True, disposition="qualified_signal", signal_id="SIG-1")
    payload.pop("signal_id")
    _append(writer, "result_screened", **payload)
    _append(writer, "route_finalized", execution_status="complete")
    _append(writer, "route_sealed")
    assert "execution_journal_signal_id_missing" in validate_worker_execution_journal(load_jsonl(writer.path))


def test_materialize_route_result_rows_is_deterministic(tmp_path):
    writer = DurableExecutionJournal(tmp_path / "journal.jsonl")
    _append(writer, "route_started")
    _append(writer, "search_returned", results_returned=6)
    _append(writer, "page_opened", result_rank=4, success=True, url="https://example.com/4")
    _append(writer, "result_screened", **_screened_payload(1, fresh=False, reject_reason="old"))
    _append(writer, "result_screened", **_screened_payload(2, fresh=True, reject_reason="scope"))
    _append(writer, "result_screened", **_screened_payload(3, fresh=False, disposition="qualified_signal", signal_id="SIG-3"))
    _append(writer, "result_screened", **_screened_payload(4, fresh=False, reject_reason="weak"))
    _append(writer, "result_screened", **_screened_payload(5, fresh=True, reject_reason="duplicate"))
    _append(writer, "result_screened", **_screened_payload(6, fresh=False, reject_reason="old"))
    _append(writer, "route_finalized", execution_status="complete")
    _append(writer, "route_sealed")
    events = load_jsonl(writer.path)
    assert validate_worker_execution_journal(events) == []

    rows = materialize_route_result_rows(
        events,
        max_result_rows=5,
        base_fields={"run_key": RUN, "attempt_id": ATTEMPT},
    )
    assert [row["result_rank"] for row in rows] == [3, 2, 5, 4, 1]
    assert rows[0]["signal_id"] == "SIG-3"
    assert rows[3]["opened"] is True
    assert all(row["row_type"] == "result" for row in rows)


def test_result_rows_cannot_be_rewritten_from_memory(tmp_path):
    events = _happy_events(tmp_path)
    rows = materialize_route_result_rows(events, max_result_rows=5)
    assert validate_result_rows_against_events(rows, events, max_result_rows=5) == []
    tampered = copy.deepcopy(rows)
    tampered[0]["result_url"] = "https://memory.example/reconstructed"
    assert "worker_audit_result_evidence_mismatch:result_url" in validate_result_rows_against_events(
        tampered, events, max_result_rows=5
    )


def test_result_row_base_fields_cannot_override_journal_evidence(tmp_path):
    events = _happy_events(tmp_path)
    try:
        materialize_route_result_rows(events, base_fields={"result_title": "memory title"})
    except ValueError as exc:
        assert str(exc) == "base_fields_must_not_override_result_evidence"
    else:
        raise AssertionError("expected ValueError")
