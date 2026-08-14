from ails_intel.fingerprint import frozen_manifest_fingerprint
from ails_intel.freeze_contract import validate_shadow_freeze_snapshot


RUN = "AILS11S-20260809-2030-BJT"
ATTEMPT = RUN + "-A1"


def _candidate(delta="d1", event="e1", disposition="selected"):
    return {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "delta_key": delta,
        "event_key_v11": event,
        "disposition": disposition,
    }


def _item(index=1, delta="d1", event="e1"):
    return {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "item_index": index,
        "title": "Example item",
        "primary_url": "https://example.org/item",
        "event_key_v11": event,
        "delta_key": delta,
        "schema_version": "v11.0",
    }


def _run(items, coverage_confidence="MEDIUM"):
    return {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "stage": "freeze",
        "state_status": "committed",
        "delivery_status": "not_started",
        "resume_stage": "report",
        "canonical_attempt": "",
        "coverage_confidence": coverage_confidence,
        "frozen_item_count": len(items),
        "selected_count": len(items),
        "write_status": "success",
        "readback_status": "success",
        "readback_match": "TRUE",
        "frozen_content_fingerprint": frozen_manifest_fingerprint(items),
    }


def test_valid_shadow_freeze_snapshot_passes():
    items = [_item()]
    errors = validate_shadow_freeze_snapshot(
        run_key=RUN,
        attempt_id=ATTEMPT,
        candidates=[_candidate()],
        daily_items=items,
        run_rows=[_run(items)],
        event_index_rows=[],
        max_items=12,
    )
    assert errors == []


def test_low_coverage_does_not_invalidate_an_integral_manifest():
    items = [_item()]
    errors = validate_shadow_freeze_snapshot(
        run_key=RUN,
        attempt_id=ATTEMPT,
        candidates=[_candidate()],
        daily_items=items,
        run_rows=[_run(items, coverage_confidence="LOW")],
        event_index_rows=[],
        max_items=12,
    )
    assert errors == []


def test_unselected_item_and_bad_fingerprint_fail():
    items = [_item()]
    run = _run(items)
    run["frozen_content_fingerprint"] = "sha256:bad"
    errors = validate_shadow_freeze_snapshot(
        run_key=RUN,
        attempt_id=ATTEMPT,
        candidates=[_candidate(disposition="rejected")],
        daily_items=items,
        run_rows=[run],
        event_index_rows=[],
        max_items=12,
    )
    assert "dailyitem_not_from_selected_candidate" in errors
    assert "selected_candidate_count_mismatch" in errors
    assert "frozen_fingerprint_mismatch" in errors


def test_shadow_eventindex_ownership_is_forbidden():
    items = [_item()]
    errors = validate_shadow_freeze_snapshot(
        run_key=RUN,
        attempt_id=ATTEMPT,
        candidates=[_candidate()],
        daily_items=items,
        run_rows=[_run(items)],
        event_index_rows=[{"last_reported_run": RUN}],
        max_items=12,
    )
    assert "shadow_eventindex_write_forbidden" in errors
