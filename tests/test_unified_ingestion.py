from ails_intel.snapshot_policy import validate_structured_snapshot_barrier
from ails_intel.unified_ingestion import (
    build_worker_coverage,
    build_worker_signal,
    enabled_structured_collector_ids,
    required_worker_routes,
    structured_snapshot_fingerprint,
    validate_unified_ingestion_snapshot,
)

RUN = "AILS11S-20260810-2030-BJT"
ATTEMPT = RUN + "-A1"
MANUAL_RUN = "AILS11M-20260810-2302-BJT"
MANUAL_ATTEMPT = MANUAL_RUN + "-A1"


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


def test_worker_signal_can_truthfully_mark_broad_science_outside_life_science_core():
    signal = build_worker_signal(
        run_key=RUN,
        attempt_id=ATTEMPT,
        batch_id="WORKER-SCIENCE",
        producer_id="chatgpt/worker",
        discovered_at_bjt="2026-08-10T21:00:00+08:00",
        channel_id="C1",
        route_id="worker/plan/SCIENCE",
        source_id="SRC-X",
        discovery_method="web_search",
        title="AI advances an open mathematics result",
        snippet="major-media evidence",
        url="https://example.com/math",
        published_at="2026-08-10",
        ai_core_hint="TRUE",
        life_science_core_hint="FALSE",
    ).values
    assert signal["ai_core_hint"] == "TRUE"
    assert signal["life_science_core_hint"] == "FALSE"


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


def test_enabled_structured_collectors_are_config_driven():
    cfg = {
        "structured_collectors_json": [
            {"id": "COL-A", "enabled": True},
            {"id": "COL-B", "enabled": False},
            {"id": "COL-C"},
        ]
    }
    assert enabled_structured_collector_ids(cfg) == {"COL-A", "COL-C"}


def _collector_coverage(collector_id, checked_at, status="complete"):
    return {
        "run_key": RUN,
        "producer_id": f"collector/{collector_id}",
        "checked_at_bjt": checked_at,
        "execution_status": status,
    }


def _frozen_structured_signal(signal_id="SIG-20260810-frozen"):
    return {
        "signal_id": signal_id,
        "run_key": RUN,
        "collection_batch_id": "STRUCTURED-1",
        "producer_id": "collector/PubMed",
        "origin_attempt_id": ATTEMPT,
        "discovered_at_bjt": "2026-08-10T19:00:00+08:00",
        "channel_id": "C3",
        "route_id": "structured/pubmed",
        "source_id": "SRC-PUBMED",
        "discovery_method": "api",
        "raw_title": "Frozen structured result",
        "raw_snippet": "evidence",
        "published_at_hint": "2026-08-10",
        "url": "https://example.com/pubmed/1",
        "stable_id": "PMID:1",
        "signal_key": "sha256:frozen",
        "priority_hint": "P1",
        "ai_core_hint": "TRUE",
        "life_science_core_hint": "TRUE",
        "signal_state": "active",
        "schema_version": "v11.0",
    }


def _frozen_structured_coverage():
    return {
        "run_key": RUN,
        "source_id": "SRC-PUBMED",
        "source_name": "PubMed",
        "source_group": "structured",
        "route": "api",
        "status": "ok",
        "hit_count": 1,
        "checked_at_bjt": "2026-08-10T19:01:00+08:00",
        "fallback_used": "FALSE",
        "retrieval_status": "complete",
        "hit_status": "hit",
        "coverage_id": "sha256:structured",
        "attempt_id": ATTEMPT,
        "producer_id": "collector/PubMed",
        "channel_id": "C3",
        "route_id": "structured/pubmed",
        "execution_status": "complete",
        "saturation_status": "clear",
        "results_seen": 1,
        "relevant_signal_count": 1,
        "schema_version": "v11.0",
    }


def _frozen_fingerprint(signals, coverage):
    return structured_snapshot_fingerprint(
        run_key=RUN,
        attempt_id=ATTEMPT,
        active_signals=signals,
        coverage_rows=coverage,
    )


def test_manual_replay_can_reference_authorized_frozen_structured_signal():
    frozen = _frozen_structured_signal()
    structured_coverage = _frozen_structured_coverage()
    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=[frozen],
        candidates=[{"source_signal_ids": frozen["signal_id"]}],
        coverage_rows=[structured_coverage],
        required_routes={},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=_frozen_fingerprint([frozen], [structured_coverage]),
    )
    assert errors == []


def test_manual_replay_rejects_cross_run_signal_without_explicit_authorization():
    frozen = _frozen_structured_signal()
    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=[frozen],
        candidates=[{"source_signal_ids": frozen["signal_id"]}],
        coverage_rows=[_frozen_structured_coverage()],
        required_routes={},
    )
    assert errors == ["candidate_references_nonactive_signal"]


def test_frozen_authorization_never_imports_source_worker_signals():
    frozen = _frozen_structured_signal()
    source_worker = build_worker_signal(
        run_key=RUN,
        attempt_id=ATTEMPT,
        batch_id="OLD-WORKER",
        producer_id="chatgpt/worker",
        discovered_at_bjt="2026-08-10T20:00:00+08:00",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        discovery_method="web_search",
        title="Old worker result",
        snippet="old evidence",
        url="https://example.com/old-worker",
        published_at="2026-08-10",
    ).values
    structured_coverage = _frozen_structured_coverage()
    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=[frozen, source_worker],
        candidates=[{"source_signal_ids": source_worker["signal_id"]}],
        coverage_rows=[structured_coverage],
        required_routes={},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=_frozen_fingerprint([frozen, source_worker], [structured_coverage]),
    )
    assert errors == ["candidate_references_nonactive_signal"]


def test_frozen_authorization_fails_closed_on_fingerprint_drift():
    frozen = _frozen_structured_signal()
    structured_coverage = _frozen_structured_coverage()
    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=[frozen],
        candidates=[{"source_signal_ids": frozen["signal_id"]}],
        coverage_rows=[structured_coverage],
        required_routes={},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint="sha256:not-the-snapshot",
    )
    assert "frozen_structured_snapshot_fingerprint_mismatch" in errors
    assert "candidate_references_nonactive_signal" in errors


def test_frozen_authorization_requires_same_report_date():
    frozen = _frozen_structured_signal()
    structured_coverage = _frozen_structured_coverage()
    other_day_manual = "AILS11M-20260811-2302-BJT"
    errors = validate_unified_ingestion_snapshot(
        run_key=other_day_manual,
        attempt_id=other_day_manual + "-A1",
        active_signals=[frozen],
        candidates=[],
        coverage_rows=[structured_coverage],
        required_routes={},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=_frozen_fingerprint([frozen], [structured_coverage]),
    )
    assert errors == ["frozen_structured_report_date_mismatch"]


def test_scheduled_shadow_cannot_enable_cross_run_frozen_authorization():
    frozen = _frozen_structured_signal()
    structured_coverage = _frozen_structured_coverage()
    other_scheduled = "AILS11S-20260810-2200-BJT"
    errors = validate_unified_ingestion_snapshot(
        run_key=other_scheduled,
        attempt_id=other_scheduled + "-A1",
        active_signals=[frozen],
        candidates=[],
        coverage_rows=[structured_coverage],
        required_routes={},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=_frozen_fingerprint([frozen], [structured_coverage]),
    )
    assert errors == ["frozen_structured_input_requires_manual_shadow"]


def test_manual_candidate_can_combine_frozen_structured_and_current_worker_signal():
    frozen = _frozen_structured_signal()
    structured_coverage = _frozen_structured_coverage()
    worker = build_worker_signal(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        batch_id="WORKER-NEW",
        producer_id="chatgpt/worker",
        discovered_at_bjt="2026-08-10T23:10:00+08:00",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        discovery_method="web_search",
        title="New manual worker result",
        snippet="new evidence",
        url="https://example.com/new-worker",
        published_at="2026-08-10",
    ).values
    worker_coverage = build_worker_coverage(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        producer_id="chatgpt/worker",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        execution_status="complete",
        checked_at_bjt="2026-08-10T23:11:00+08:00",
        relevant_signal_count=1,
    ).values
    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=[frozen, worker],
        candidates=[{"source_signal_ids": [frozen["signal_id"], worker["signal_id"]]}],
        coverage_rows=[structured_coverage, worker_coverage],
        required_routes={"C1": {"worker/c1/broad/01"}},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=_frozen_fingerprint([frozen], [structured_coverage]),
    )
    assert errors == []


def test_structured_snapshot_fingerprint_is_order_independent_and_detects_drift():
    first = _frozen_structured_signal("SIG-20260810-a")
    second = _frozen_structured_signal("SIG-20260810-b")
    second["signal_key"] = "sha256:second"
    second["url"] = "https://example.com/pubmed/2"
    coverage = _frozen_structured_coverage()
    baseline = _frozen_fingerprint([first, second], [coverage])
    assert baseline == _frozen_fingerprint([second, first], [coverage])
    second["raw_title"] = "Mutated title"
    assert baseline != _frozen_fingerprint([first, second], [coverage])


def test_structured_snapshot_barrier_accepts_fresh_partial_and_failed_collectors():
    coverage = [
        _collector_coverage("COL-A", "2026-08-10T19:10:00+08:00", "partial"),
        _collector_coverage("COL-B", "2026-08-10T19:12:00+08:00", "failed"),
    ]
    errors = validate_structured_snapshot_barrier(
        run_key=RUN,
        report_date="2026-08-10",
        coverage_rows=coverage,
        expected_collector_ids={"COL-A", "COL-B"},
        not_before_bjt="18:00:00",
        current_active_signal_count=10,
        declared_signal_count=10,
    )
    assert errors == []


def test_structured_snapshot_barrier_detects_missing_stale_and_drift():
    coverage = [
        _collector_coverage("COL-A", "2026-08-10T17:59:59+08:00", "complete"),
    ]
    errors = validate_structured_snapshot_barrier(
        run_key=RUN,
        report_date="2026-08-10",
        coverage_rows=coverage,
        expected_collector_ids={"COL-A", "COL-B"},
        not_before_bjt="18:00:00",
        current_active_signal_count=12,
        declared_signal_count=10,
    )
    assert "structured_snapshot_stale_collector" in errors
    assert "structured_snapshot_missing_collector" in errors
    assert "signal_count_snapshot_drift" in errors


def test_structured_snapshot_barrier_rejects_nonterminal_collector():
    errors = validate_structured_snapshot_barrier(
        run_key=RUN,
        report_date="2026-08-10",
        coverage_rows=[_collector_coverage("COL-A", "2026-08-10T19:00:00+08:00", "running")],
        expected_collector_ids={"COL-A"},
        not_before_bjt="18:00",
    )
    assert errors == ["structured_snapshot_nonterminal_collector"]
