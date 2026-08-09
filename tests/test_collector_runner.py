from ails_intel.collector_runner import existing_signal_action, signal_priority_for_channel


def test_structured_signal_priority_is_not_source_priority():
    assert signal_priority_for_channel("C1") == "P1"
    assert signal_priority_for_channel("C3") == "P1"
    assert signal_priority_for_channel("C4") == "P1"
    assert signal_priority_for_channel("C5") == "P2"


def test_existing_signal_action_new_when_absent():
    assert existing_signal_action(None) == "new"


def test_existing_signal_action_duplicates_active_signal():
    assert existing_signal_action({"state": "active", "notes": ""}) == "duplicate"


def test_existing_signal_action_reactivates_only_first_run_diagnostic_invalidations():
    assert existing_signal_action(
        {"state": "invalid", "notes": "diagnostic_first_run_pre_sprint2.1"}
    ) == "reactivate"
    assert existing_signal_action(
        {"state": "invalid", "notes": "bad_source_payload"}
    ) == "duplicate"
