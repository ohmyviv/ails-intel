from ails_intel.snapshot_policy import barrier_required_structured_collector_ids


def test_no_individual_collector_is_a_hard_barrier_input():
    cfg = {
        "structured_collectors_json": [
            {"id": "COL-A", "enabled": True},
            {"id": "COL-B"},
            {"id": "COL-C", "enabled": False},
            {"id": "COL-LEGACY-HARD", "enabled": True, "barrier_required": True},
        ]
    }
    assert barrier_required_structured_collector_ids(cfg) == set()


def test_legacy_probation_and_barrier_flags_do_not_change_source_level_blocking():
    cfg = {
        "structured_collectors_json": [
            {"id": "COL-CORE", "enabled": True},
            {"id": "COL-PROBATION", "enabled": True, "barrier_required": False},
            {"id": "COL-PROBATION-TEXT", "enabled": True, "barrier_required": "false"},
        ]
    }
    assert barrier_required_structured_collector_ids(cfg) == set()
