from datetime import date, datetime, timezone

import pytest

from ails_intel.source_schedule import (
    DATE_MOD_3_GROUP_REMAINDERS,
    date_mod_3_bucket,
    local_calendar_date,
    rotation_group_due,
    source_required_today,
)


def test_group_mapping_is_explicit_and_stable():
    assert DATE_MOD_3_GROUP_REMAINDERS == {"A": 0, "B": 1, "C": 2}


def test_consecutive_days_rotate_a_b_c_without_reset():
    assert date_mod_3_bucket(date(2026, 8, 14)) == 0
    assert date_mod_3_bucket(date(2026, 8, 15)) == 1
    assert date_mod_3_bucket(date(2026, 8, 16)) == 2
    assert date_mod_3_bucket(date(2026, 8, 17)) == 0


def test_rotation_continues_across_month_boundary():
    assert date_mod_3_bucket(date(2026, 8, 31)) == 2
    assert date_mod_3_bucket(date(2026, 9, 1)) == 0
    assert date_mod_3_bucket(date(2026, 9, 2)) == 1


def test_src008_group_a_is_not_due_on_aug_15_and_due_on_aug_17():
    assert not source_required_today(
        local_date=date(2026, 8, 15),
        required_today_rule="date_mod_3",
        rotation_group="A",
    )
    assert source_required_today(
        local_date=date(2026, 8, 17),
        required_today_rule="date_mod_3",
        rotation_group="A",
    )


def test_daily_rule_remains_daily_and_inactive_source_is_not_due():
    assert source_required_today(
        local_date=date(2026, 8, 15),
        required_today_rule="all_active_daily",
        rotation_group="",
    )
    assert not source_required_today(
        local_date=date(2026, 8, 15),
        required_today_rule="all_active_daily",
        status="inactive",
    )


def test_unknown_rule_or_group_is_not_guessed():
    with pytest.raises(ValueError):
        source_required_today(
            local_date=date(2026, 8, 15),
            required_today_rule="date_mod_3",
            rotation_group="D",
        )
    with pytest.raises(ValueError):
        source_required_today(
            local_date=date(2026, 8, 15),
            required_today_rule="some_future_rule",
            rotation_group="A",
        )


def test_reporting_timezone_controls_calendar_date():
    # 2026-08-14 16:30 UTC is already 2026-08-15 in Asia/Shanghai.
    when = datetime(2026, 8, 14, 16, 30, tzinfo=timezone.utc)
    assert local_calendar_date(when, "Asia/Shanghai") == date(2026, 8, 15)


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        local_calendar_date(datetime(2026, 8, 15, 12, 0), "Asia/Shanghai")


def test_group_due_helper_matches_mapping():
    assert rotation_group_due(date(2026, 8, 14), "A")
    assert rotation_group_due(date(2026, 8, 15), "B")
    assert rotation_group_due(date(2026, 8, 16), "C")
