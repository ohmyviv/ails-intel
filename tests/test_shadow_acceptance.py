from copy import deepcopy

from ails_intel.fingerprint import frozen_manifest_fingerprint
from ails_intel.shadow_acceptance import evaluate_shadow_acceptance
from ails_intel.signal_keys import make_coverage_id

RUN = "AILS11S-20260815-2030-BJT"
ATTEMPT = RUN + "-A1"
ROUTE = "worker/plan/P1"


def _fixture():
    cfg = {
        "structured_collectors_json": [
            {"id": "COL-A", "enabled": True},
            {"id": "COL-B", "enabled": True, "barrier_required": False},
        ],
        "collector_snapshot_not_before_bjt": "18:00:00",
        "worker_route_audit_max_result_rows_per_route": 5,
        "max_items": 12,
    }
    signal = {
        "signal_id": "SIG-W1",
        "run_key": RUN,
        "producer_id": "chatgpt/worker",
        "origin_attempt_id": ATTEMPT,
        "channel_id": "C1",
        "route_id": ROUTE,
        "signal_state": "active",
        "raw_title": "AI biotech financing",
        "url": "https://example.org/story",
        "schema_version": "v11.0",
    }
    worker_coverage = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "channel_id": "C1",
        "route_id": ROUTE,
        "source_id": "",
        "coverage_id": make_coverage_id(RUN, "chatgpt/worker", ATTEMPT, "C1", ROUTE, ""),
        "execution_status": "complete",
        "results_seen": "1",
        "relevant_signal_count": "1",
    }
    coverage = [
        {
            "run_key": RUN,
            "producer_id": "collector/COL-A",
            "execution_status": "complete",
            "checked_at_bjt": "2026-08-15T20:31:00+08:00",
        },
        {
            "run_key": RUN,
            "producer_id": "collector/COL-B",
            "execution_status": "complete",
            "checked_at_bjt": "2026-08-15T20:31:01+08:00",
        },
        worker_coverage,
    ]
    candidate = {
        "candidate_id": "CAN-1",
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "source_signal_ids": "SIG-W1",
        "event_key_v11": "EV-1",
        "delta_key": "DELTA-1",
        "disposition": "selected",
    }
    item = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "item_index": "1",
        "title": "AI biotech financing",
        "primary_url": "https://example.org/story",
        "event_key_v11": "EV-1",
        "delta_key": "DELTA-1",
    }
    run = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "report_date": "2026-08-15",
        "completed_at_bjt": "2026-08-15T21:20:00+08:00",
        "stage": "completed",
        "final_status": "shadow_passed",
        "state_status": "passed",
        "delivery_status": "delivered",
        "resume_stage": "passed",
        "canonical_attempt": "",
        "transaction_id": ATTEMPT,
        "schema_version": "v11.1",
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
            "results_screened": "1",
            "qualifying_results": "1",
        },
        {
            "audit_id": "AUD-RESULT",
            "run_key": RUN,
            "attempt_id": ATTEMPT,
            "producer_id": "chatgpt/worker",
            "channel_id": "C1",
            "route_id": ROUTE,
            "row_type": "result",
            "disposition": "qualified_signal",
            "signal_id": "SIG-W1",
        },
    ]
    return {
        "report_date": "2026-08-15",
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "cfg": cfg,
        "run_rows": [run],
        "active_signals": [signal],
        "candidates": [candidate],
        "coverage_rows": coverage,
        "worker_audit_rows": audits,
        "daily_items": [item],
        "event_index_rows": [],
        "required_routes": {"C1": {ROUTE}},
    }


def _retarget_to_aug14(data):
    old_attempt = data["attempt_id"]
    run_key = "AILS11S-20260814-2030-BJT"
    attempt = run_key + "-A2"
    data["report_date"] = "2026-08-14"
    data["run_key"] = run_key
    data["attempt_id"] = attempt
    run = data["run_rows"][0]
    run.update({
        "run_key": run_key,
        "attempt_id": attempt,
        "report_date": "2026-08-14",
        "completed_at_bjt": "2026-08-14T23:30:00+08:00",
        "transaction_id": attempt,
    })
    for row in data["active_signals"]:
        row.update({"run_key": run_key, "origin_attempt_id": attempt})
    for row in data["candidates"]:
        row.update({"run_key": run_key, "attempt_id": attempt})
    for row in data["coverage_rows"]:
        row["run_key"] = run_key
        if str(row.get("producer_id", "")).startswith("collector/"):
            row["checked_at_bjt"] = "2026-08-14T23:10:00+08:00"
        if row.get("attempt_id") == old_attempt:
            row["attempt_id"] = attempt
            row["coverage_id"] = make_coverage_id(
                run_key, "chatgpt/worker", attempt, "C1", ROUTE, ""
            )
    for row in data["worker_audit_rows"]:
        row.update({"run_key": run_key, "attempt_id": attempt})
    for row in data["daily_items"]:
        row.update({"run_key": run_key, "attempt_id": attempt})
    run["frozen_content_fingerprint"] = frozen_manifest_fingerprint(data["daily_items"])
    return data


def test_post_run_ledger_acceptance_passes_and_archive_stays_external():
    result = evaluate_shadow_acceptance(**_fixture())
    assert result.ledger_verdict == "PASS"
    assert result.source_failure_path == "NOT_EXERCISED"
    assert result.errors == ()
    assert result.metrics["archive_check"] == "EXTERNAL_REQUIRED"
    assert "archive_body_readback_external" in result.warnings


def test_failed_collector_is_terminal_and_worker_continuation_passes():
    data = _fixture()
    data["coverage_rows"][1]["execution_status"] = "failed"
    data["run_rows"][0]["coverage_confidence_pre_rescue"] = "LOW"
    data["run_rows"][0]["coverage_confidence"] = "LOW"
    data["run_rows"][0]["rescue_triggered"] = "TRUE"
    result = evaluate_shadow_acceptance(**data)
    assert result.ledger_verdict == "PASS"
    assert result.source_failure_path == "PASS"
    assert result.metrics["failed_or_skipped_collector_count"] == 1


def test_failed_collector_without_worker_continuation_is_a_regression():
    data = _fixture()
    data["coverage_rows"][1]["execution_status"] = "failed"
    data["coverage_rows"] = data["coverage_rows"][:2]
    result = evaluate_shadow_acceptance(**data)
    assert result.source_failure_path == "FAIL"
    assert "SOURCE_FAILURE_WITHOUT_WORKER_CONTINUATION" in result.errors


def test_missing_collector_observation_remains_fail_closed():
    data = _fixture()
    data["coverage_rows"] = [
        row for row in data["coverage_rows"]
        if row.get("producer_id") != "collector/COL-B"
    ]
    result = evaluate_shadow_acceptance(**data)
    assert result.ledger_verdict == "FAIL"
    assert "structured_snapshot_missing_collector" in result.errors


def test_low_post_rescue_is_not_itself_a_transaction_failure():
    data = _fixture()
    data["run_rows"][0]["coverage_confidence_pre_rescue"] = "LOW"
    data["run_rows"][0]["coverage_confidence"] = "LOW"
    data["run_rows"][0]["rescue_triggered"] = "TRUE"
    result = evaluate_shadow_acceptance(**data)
    assert result.ledger_verdict == "PASS"


def test_manual_aug14_regression_can_force_continuation_check():
    data = _retarget_to_aug14(_fixture())
    data["coverage_rows"][1]["execution_status"] = "failed"
    natural_policy = evaluate_shadow_acceptance(**deepcopy(data))
    assert natural_policy.source_failure_path == "NOT_ENFORCED_PRE_EFFECTIVE_DATE"
    data["enforce_continuation"] = True
    forced = evaluate_shadow_acceptance(**data)
    assert forced.source_failure_path == "PASS"
