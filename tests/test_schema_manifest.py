from ails_intel.schema_manifest import EXPECTED_HEADERS

def test_signal_width():
    assert len(EXPECTED_HEADERS["Lite_Signals"]) == 28

def test_run_width():
    assert len(EXPECTED_HEADERS["Lite_Runs"]) == 66

def test_no_duplicate_headers():
    for name, headers in EXPECTED_HEADERS.items():
        assert len(headers) == len(set(headers)), name
