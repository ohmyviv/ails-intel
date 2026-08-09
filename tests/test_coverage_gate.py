from ails_intel.coverage_gate import evaluate_coverage, plan_rescue, validate_gate_snapshot


MANDATORY = ["C1", "C2", "C3", "C4", "C6"]


def test_missing_mandatory_channels_and_premium_force_low():
    decision = evaluate_coverage(
        channel_health={"C3": "complete", "C5": "partial"},
        mandatory_channels=MANDATORY,
        premium_sweep_complete=False,
        unresolved_gap=False,
        abnormal_low_signal=False,
        collector_saturation_count=1,
        pending_p0_due_count=0,
    )
    assert decision.confidence == "LOW"
    assert decision.mandatory_completed == 1
    assert decision.mandatory_missing == 4
    assert "c1_failed_or_missing" in decision.reasons
    assert "c2_failed_or_missing" in decision.reasons
    assert "premium_sweep_incomplete" in decision.reasons


def test_one_partial_or_saturation_is_medium_when_no_low_condition():
    decision = evaluate_coverage(
        channel_health={"C1": "complete", "C2": "complete", "C3": "complete", "C4": "complete", "C6": "partial"},
        mandatory_channels=MANDATORY,
        premium_sweep_complete=True,
        unresolved_gap=False,
        abnormal_low_signal=False,
        collector_saturation_count=1,
        pending_p0_due_count=0,
    )
    assert decision.confidence == "MEDIUM"
    assert "mandatory_partial_eq_1" in decision.reasons
    assert "collector_saturation" in decision.reasons


def test_high_requires_clean_mandatory_and_premium_coverage():
    decision = evaluate_coverage(
        channel_health={channel: "complete" for channel in MANDATORY},
        mandatory_channels=MANDATORY,
        premium_sweep_complete=True,
        unresolved_gap=False,
        abnormal_low_signal=False,
        collector_saturation_count=0,
        pending_p0_due_count=0,
    )
    assert decision.confidence == "HIGH"
    assert decision.mandatory_completed == 5


def test_rescue_required_for_low_or_recent_critical_miss():
    rescue = plan_rescue(
        pre_rescue_confidence="LOW",
        previous_gap=False,
        abnormal_low_signal=False,
        rolling_critical_miss_count=1,
        broad_search_max=4,
        max_new_candidates=3,
    )
    assert rescue.required is True
    assert rescue.broad_search_max == 4
    assert rescue.max_new_candidates == 3
    assert set(rescue.reasons) == {"coverage_low", "rolling_critical_miss"}


def test_no_rescue_when_gate_is_clean_and_no_trigger():
    rescue = plan_rescue(
        pre_rescue_confidence="HIGH",
        previous_gap=False,
        abnormal_low_signal=False,
        rolling_critical_miss_count=0,
    )
    assert rescue.required is False
    assert rescue.broad_search_max == 0
    assert rescue.premium_sweep is False
    assert rescue.tier_a_exact_sweep is False


def _ready_run():
    return {
        "stage": "coverage_gate",
        "final_status": "ready_for_freeze",
        "resume_stage": "freeze",
        "state_status": "verified",
        "delivery_status": "not_started",
        "canonical_attempt": "",
        "coverage_confidence_pre_rescue": "LOW",
        "coverage_confidence": "MEDIUM",
        "coverage_gate_reason": "pre low; post medium",
        "mandatory_channels_completed": "5",
        "mandatory_channels_total": "5",
        "rescue_triggered": "TRUE",
    }


def test_gate_snapshot_accepts_medium_ready_for_freeze():
    errors = validate_gate_snapshot(
        run=_ready_run(),
        mandatory_channels=MANDATORY,
        channel_health={channel: "complete" for channel in MANDATORY} | {"C5": "partial"},
        daily_items_for_run=0,
        event_index_ownership_count=0,
    )
    assert errors == []


def test_gate_snapshot_rejects_low_or_premature_writes():
    run = _ready_run()
    run["coverage_confidence"] = "LOW"
    errors = validate_gate_snapshot(
        run=run,
        mandatory_channels=MANDATORY,
        channel_health={"C1": "complete", "C2": "complete", "C3": "complete", "C4": "partial", "C6": "partial"},
        daily_items_for_run=1,
        event_index_ownership_count=1,
    )
    assert "final_coverage_still_low" in errors
    assert "mandatory_channel_not_complete" in errors
    assert "dailyitems_written_before_freeze" in errors
    assert "eventindex_written_in_shadow" in errors
