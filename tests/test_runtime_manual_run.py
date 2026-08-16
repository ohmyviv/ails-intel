from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from ails_intel.runtime import build_run_key, resolve_report_date, resolve_run_key


def _entry(value):
    return SimpleNamespace(value=value)


def _cfg(mode="shadow"):
    return {
        "execution_mode": _entry(mode),
        "shadow_run_prefix": _entry("AILS11S"),
        "production_run_prefix": _entry("AILS11P"),
        "report_cutoff_hour_bjt": _entry(20),
        "report_cutoff_minute_bjt": _entry(30),
    }


def _now():
    return datetime(2026, 8, 16, 22, 45, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_scheduled_run_key_remains_config_derived():
    assert build_run_key(_cfg(), _now()) == "AILS11S-20260816-2030-BJT"
    assert resolve_run_key(_cfg(), _now()) == "AILS11S-20260816-2030-BJT"


def test_manual_run_key_uses_isolated_namespace():
    assert resolve_run_key(
        _cfg(),
        _now(),
        "AILS11M-20260816-2245-BJT",
    ) == "AILS11M-20260816-2245-BJT"


def test_manual_run_key_cannot_reuse_shadow_or_production_namespace():
    with pytest.raises(RuntimeError, match="isolated namespace"):
        resolve_run_key(_cfg(), _now(), "AILS11S-20260816-2030-BJT")
    with pytest.raises(RuntimeError, match="isolated namespace"):
        resolve_run_key(_cfg(), _now(), "AILS11P-20260816-2030-BJT")


def test_manual_run_key_requires_shadow_mode():
    with pytest.raises(RuntimeError, match="requires shadow mode"):
        resolve_run_key(_cfg(mode="production"), _now(), "AILS11M-20260816-2245-BJT")


def test_manual_run_key_rejects_unsafe_characters():
    with pytest.raises(RuntimeError, match="invalid manual run_key"):
        resolve_run_key(_cfg(), _now(), "AILS11M 20260816")


def test_report_date_defaults_to_now_and_accepts_backdated_target():
    assert resolve_report_date("", _now()).isoformat() == "2026-08-16"
    assert resolve_report_date("2026-08-15", _now()).isoformat() == "2026-08-15"


def test_report_date_rejects_invalid_value():
    with pytest.raises(RuntimeError, match="invalid report_date"):
        resolve_report_date("2026/08/16", _now())
