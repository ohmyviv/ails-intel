from datetime import date

from ails_intel.watchdog import _shadow_continuation_check


class _CfgValue:
    def __init__(self, value):
        self.value = value


def _cfg():
    return {
        "shadow_run_prefix": _CfgValue("AILS11S"),
        "collector_snapshot_not_before_bjt": _CfgValue("18:00:00"),
        "structured_collectors_json": _CfgValue([
            {"id": "COL-A", "enabled": True},
            {"id": "COL-B", "enabled": True},
        ]),
    }


def _rows(with_worker: bool):
    run_rows = [["AILS11S-20260815-2030-BJT", "AILS11S-20260815-2030-BJT-A1", "2026-08-15T20:55:00+08:00"]]
    run_pos = {"run_key": 0, "attempt_id": 1, "completed_at_bjt": 2}
    coverage_pos = {
        "run_key": 0,
        "producer_id": 1,
        "checked_at_bjt": 2,
        "execution_status": 3,
        "attempt_id": 4,
    }
    coverage_rows = [
        ["AILS11S-20260815-2030-BJT", "collector/COL-A", "2026-08-15T20:33:00+08:00", "failed", ""],
        ["AILS11S-20260815-2030-BJT", "collector/COL-B", "2026-08-15T20:33:01+08:00", "complete", ""],
    ]
    if with_worker:
        coverage_rows.append([
            "AILS11S-20260815-2030-BJT",
            "chatgpt/worker",
            "2026-08-15T20:42:00+08:00",
            "complete",
            "AILS11S-20260815-2030-BJT-A1",
        ])
    return run_rows, run_pos, coverage_rows, coverage_pos


def test_watchdog_fails_when_terminal_source_failure_is_followed_by_no_worker():
    run_rows, run_pos, coverage_rows, coverage_pos = _rows(with_worker=False)
    result = _shadow_continuation_check(
        run_rows=run_rows,
        run_pos=run_pos,
        coverage_rows=coverage_rows,
        coverage_pos=coverage_pos,
        cfg=_cfg(),
        day=date(2026, 8, 15),
        suffix="2030-BJT",
    )
    assert result["evaluated"] is True
    assert result["ok"] is False
    assert result["error_code"] == "SOURCE_FAILURE_WITHOUT_WORKER_CONTINUATION"


def test_watchdog_passes_when_worker_continues_after_terminal_source_failure():
    run_rows, run_pos, coverage_rows, coverage_pos = _rows(with_worker=True)
    result = _shadow_continuation_check(
        run_rows=run_rows,
        run_pos=run_pos,
        coverage_rows=coverage_rows,
        coverage_pos=coverage_pos,
        cfg=_cfg(),
        day=date(2026, 8, 15),
        suffix="2030-BJT",
    )
    assert result["evaluated"] is True
    assert result["ok"] is True
    assert result["failed_collectors"] == 1
    assert result["worker_rows"] == 1


def test_watchdog_does_not_retroactively_fail_august_14_incident():
    run_rows, run_pos, coverage_rows, coverage_pos = _rows(with_worker=False)
    run_rows[0][0] = "AILS11S-20260814-2030-BJT"
    coverage_rows[0][0] = "AILS11S-20260814-2030-BJT"
    coverage_rows[1][0] = "AILS11S-20260814-2030-BJT"
    result = _shadow_continuation_check(
        run_rows=run_rows,
        run_pos=run_pos,
        coverage_rows=coverage_rows,
        coverage_pos=coverage_pos,
        cfg=_cfg(),
        day=date(2026, 8, 14),
        suffix="2030-BJT",
    )
    assert result["evaluated"] is False
    assert result["ok"] is True
