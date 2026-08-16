from ails_intel.models import CoverageRecord
from ails_intel.snapshot_policy import validate_structured_snapshot_barrier
from ails_intel.structured_signal_identity import (
    assign_persisted_relevant_signal_counts,
    make_structured_route_identity,
    reconcile_expected_structured_signal_sets,
    structured_active_signal_sets,
    structured_signal_set_digest,
    validate_structured_coverage_signal_identity,
)


RUN_KEY = "AILS11S-20260816-2030-BJT"
CHECKED_AT = "2026-08-16T20:40:00+08:00"


def _signal(
    signal_key: str,
    *,
    collector_id: str = "COL-BIORXIV",
    channel_id: str = "C5",
    route_id: str = "api/COL-BIORXIV",
    source_id: str = "SRC-019",
):
    return {
        "run_key": RUN_KEY,
        "producer_id": f"collector/{collector_id}",
        "channel_id": channel_id,
        "route_id": route_id,
        "source_id": source_id,
        "signal_key": signal_key,
        "signal_state": "active",
    }


def _coverage(
    relevant_signal_count: int,
    *,
    hit_count: int | None = None,
    collector_id: str = "COL-BIORXIV",
    channel_id: str = "C5",
    route_id: str = "api/COL-BIORXIV",
    source_id: str = "SRC-019",
    execution_status: str = "complete",
):
    return {
        "run_key": RUN_KEY,
        "producer_id": f"collector/{collector_id}",
        "channel_id": channel_id,
        "route_id": route_id,
        "source_id": source_id,
        "relevant_signal_count": relevant_signal_count,
        "hit_count": relevant_signal_count if hit_count is None else hit_count,
        "execution_status": execution_status,
        "checked_at_bjt": CHECKED_AT,
    }


def test_readback_count_separates_raw_hits_from_unique_persisted_signals():
    active_signals = [_signal(f"key-{i}") for i in range(42)]
    signal_sets, errors = structured_active_signal_sets(
        run_key=RUN_KEY,
        active_signals=active_signals,
    )
    assert errors == []

    record = CoverageRecord(_coverage(43, hit_count=43))
    assign_errors = assign_persisted_relevant_signal_counts(
        coverage_records=[record],
        persisted_signal_sets=signal_sets,
    )

    assert assign_errors == []
    assert record.values["hit_count"] == 43
    assert record.values["relevant_signal_count"] == 42


def test_expected_signal_set_accepts_one_duplicate_raw_identity():
    route = make_structured_route_identity(
        "collector/COL-BIORXIV", "C5", "api/COL-BIORXIV", "SRC-019"
    )
    raw_keys = [f"key-{i}" for i in range(42)] + ["key-0"]
    expected = {route: set(raw_keys)}
    persisted = {route: {f"key-{i}" for i in range(42)}}

    assert len(raw_keys) == 43
    assert len(expected[route]) == 42
    assert reconcile_expected_structured_signal_sets(
        expected_signal_sets=expected,
        persisted_signal_sets=persisted,
    ) == []


def test_expected_signal_set_rejects_true_write_loss():
    route = make_structured_route_identity(
        "collector/COL-BIORXIV", "C5", "api/COL-BIORXIV", "SRC-019"
    )
    expected = {route: {f"key-{i}" for i in range(43)}}
    persisted = {route: {f"key-{i}" for i in range(42)}}

    assert reconcile_expected_structured_signal_sets(
        expected_signal_sets=expected,
        persisted_signal_sets=persisted,
    ) == ["structured_signal_set_identity_mismatch"]


def test_snapshot_barrier_accepts_43_raw_observations_42_unique_signals():
    active_signals = [_signal(f"key-{i}") for i in range(42)]
    errors = validate_structured_snapshot_barrier(
        run_key=RUN_KEY,
        report_date="2026-08-16",
        coverage_rows=[_coverage(42, hit_count=43)],
        expected_collector_ids={"COL-BIORXIV"},
        current_active_signal_count=42,
        declared_signal_count=42,
        active_signal_rows=active_signals,
    )

    assert errors == []


def test_snapshot_barrier_rejects_coverage_43_when_persisted_set_is_42():
    active_signals = [_signal(f"key-{i}") for i in range(42)]
    errors = validate_structured_snapshot_barrier(
        run_key=RUN_KEY,
        report_date="2026-08-16",
        coverage_rows=[_coverage(43, hit_count=43)],
        expected_collector_ids={"COL-BIORXIV"},
        current_active_signal_count=42,
        declared_signal_count=42,
        active_signal_rows=active_signals,
    )

    assert "structured_signal_set_identity_mismatch" in errors


def test_per_route_identity_catches_mismatch_hidden_by_equal_global_total():
    coverage_rows = [
        _coverage(
            1,
            collector_id="COL-A",
            channel_id="C1",
            route_id="api/COL-A",
            source_id="SRC-A",
        ),
        _coverage(
            1,
            collector_id="COL-B",
            channel_id="C2",
            route_id="api/COL-B",
            source_id="SRC-B",
        ),
    ]
    active_signals = [
        _signal(
            "key-a1",
            collector_id="COL-A",
            channel_id="C1",
            route_id="api/COL-A",
            source_id="SRC-A",
        ),
        _signal(
            "key-a2",
            collector_id="COL-A",
            channel_id="C1",
            route_id="api/COL-A",
            source_id="SRC-A",
        ),
    ]

    errors = validate_structured_snapshot_barrier(
        run_key=RUN_KEY,
        report_date="2026-08-16",
        coverage_rows=coverage_rows,
        expected_collector_ids={"COL-A", "COL-B"},
        current_active_signal_count=2,
        declared_signal_count=2,
        active_signal_rows=active_signals,
    )

    assert errors == ["structured_signal_set_identity_mismatch"]


def test_terminal_collector_failure_remains_coverage_degradation_not_identity_failure():
    errors = validate_structured_snapshot_barrier(
        run_key=RUN_KEY,
        report_date="2026-08-16",
        coverage_rows=[_coverage(0, hit_count=0, execution_status="failed")],
        expected_collector_ids={"COL-BIORXIV"},
        current_active_signal_count=0,
        declared_signal_count=0,
        active_signal_rows=[],
    )

    assert errors == []


def test_duplicate_active_signal_key_is_integrity_failure():
    active_signals = [_signal("dup-key"), _signal("dup-key")]
    errors = validate_structured_coverage_signal_identity(
        run_key=RUN_KEY,
        coverage_rows=[_coverage(1)],
        active_signals=active_signals,
    )

    assert "structured_signal_key_duplicate" in errors


def test_signal_set_digest_is_order_independent_and_set_based():
    assert structured_signal_set_digest(["b", "a", "a"]) == structured_signal_set_digest(["a", "b"])
    assert structured_signal_set_digest(["a", "b"]) != structured_signal_set_digest(["a", "c"])
