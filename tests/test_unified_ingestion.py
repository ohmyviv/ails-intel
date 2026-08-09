from ails_intel.unified_ingestion import (
    build_worker_coverage,
    build_worker_signal,
    required_worker_routes,
    validate_unified_ingestion_snapshot,
)

RUN = "AILS11S-20260810-2030-BJT"
ATTEMPT = RUN + "-A1"


def test_required_routes_include_broad_sources_plans_and_p0_entities():
    cfg = {
        "worker_channel_plan_map_json": {"C1": ["P1"], "C4": ["P4"], "C6": ["P6"]},
        "c1_required_broad_query_count": 2,
        "c1_premium_sources_json": ["SRC-A"],
        "c1_specialist_sources_json": ["SRC-B"],
    }
    entities = [
        {"entity_id": "ENT-1", "status": "active", "priority": "P0"},
        {"entity_id": "ENT-2", "status": "active", "priority": "P1"},
    ]
    routes = required_worker_routes(cfg, entities)
    assert routes["C1"] == {
        "worker/plan/P1",
        "worker/c1/broad/01",
        "worker/c1/broad/02",
        "worker/source/SRC-A",
        "worker/source/SRC-B",
    }
    assert routes["C2"] == {"worker/entity/ENT-1"}
    assert routes["C4"] == {"worker/plan/P4"}
    assert routes["C6"] == {"worker/plan/P6"}


def test_worker_signal_and_coverage_form_one_auditable_route():
    signal = build_worker_signal(
        run_key=RUN,
        attempt_id=ATTEMPT,
        batch_id="WORKER-1",
        producer_id="chatgpt/worker",
        discovered_at_bjt="2026-08-10T21:00:00+08:00",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        discovery_method="web_search",
        title="AI biotech raises new financing",
        snippet="primary facts",
        url="https://example.com/story",
        published_at="2026-08-10",
    ).values
    coverage = build_worker_coverage(
        run_key=RUN,
        attempt_id=ATTEMPT,
        producer_id="chatgpt/worker",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        source_name="Example",
        execution_status="complete",
        checked_at_bjt="2026-08-10T21:01:00+08:00",
        relevant_signal_count=1,
        results_seen=4,
        representative_url="https://example.com/story",
    ).values
    candidate = {"source_signal_ids": signal["signal_id"]}
    errors = validate_unified_ingestion_snapshot(
        run_key=RUN,
        attempt_id=ATTEMPT,
        active_signals=[signal],
        candidates=[candidate],
        coverage_rows=[coverage],
        required_routes={"C1": {"worker/c1/broad/01"}},
        channel_health={"C1": "complete"},
    )
    assert errors == []


def test_complete_channel_cannot_hide_missing_route():
    errors = validate_unified_ingestion_snapshot(
        run_key=RUN,
        attempt_id=ATTEMPT,
        active_signals=[],
        candidates=[],
        coverage_rows=[],
        required_routes={"C1": {"worker/c1/broad/01"}},
        channel_health={"C1": "complete"},
    )
    assert "required_route_missing:C1" in errors
