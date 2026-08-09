from ails_intel.collector_runner import signal_priority_for_channel


def test_structured_signal_priority_is_not_source_priority():
    assert signal_priority_for_channel("C3") == "P1"
    assert signal_priority_for_channel("C5") == "P2"
    assert signal_priority_for_channel("C1") == "P2"
