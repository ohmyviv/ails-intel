import pytest
from ails_intel.safe_logger import log_event


def test_unknown_log_field_rejected():
    with pytest.raises(ValueError):
        log_event("x", private_config="do-not-log")


def test_allowed_log_fields(capsys):
    log_event("x", component="test", status="PASS", error_count=0)
    out = capsys.readouterr().out
    assert '"status":"PASS"' in out
