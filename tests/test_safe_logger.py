import pytest
from ails_intel.safe_logger import log_event


def test_unknown_log_field_rejected():
    with pytest.raises(ValueError):
        log_event("x", private_config="do-not-log")


def test_allowed_log_fields(capsys):
    log_event(
        "x",
        component="test",
        status="PASS",
        error_count=0,
        reactivated_count=3,
        report_date="2026-08-16",
        run_type="manual_rerun",
    )
    out = capsys.readouterr().out
    assert '"status":"PASS"' in out
    assert '"reactivated_count":3' in out
    assert '"report_date":"2026-08-16"' in out
    assert '"run_type":"manual_rerun"' in out
