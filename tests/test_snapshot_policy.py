from ails_intel.snapshot_policy import barrier_required_structured_collector_ids


def test_barrier_required_collectors_default_fail_closed():
    cfg = {
        "structured_collectors_json": [
            {"id": "COL-A", "enabled": True},
            {"id": "COL-B"},
            {"id": "COL-C", "enabled": False},
        ]
    }
    assert barrier_required_structured_collector_ids(cfg) == {"COL-A", "COL-B"}


def test_probation_collector_runs_but_is_not_a_hard_barrier_input():
    cfg = {
        "structured_collectors_json": [
            {"id": "COL-CORE", "enabled": True},
            {"id": "COL-PROBATION", "enabled": True, "barrier_required": False},
            {"id": "COL-PROBATION-TEXT", "enabled": True, "barrier_required": "false"},
        ]
    }
    assert barrier_required_structured_collector_ids(cfg) == {"COL-CORE"}
