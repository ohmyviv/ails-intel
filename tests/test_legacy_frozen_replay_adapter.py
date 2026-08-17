import pytest

from ails_intel.legacy_frozen_replay import (
    legacy_structured_snapshot_fingerprint,
    qualify_legacy_frozen_structured_snapshot,
)
from ails_intel.unified_ingestion import (
    build_worker_coverage,
    build_worker_signal,
    validate_unified_ingestion_snapshot,
)

RUN = "AILS11S-20260817-2030-BJT"
ATTEMPT = RUN + "-A1"
MANUAL_RUN = "AILS11M-20260817-2316-BJT"
MANUAL_ATTEMPT = MANUAL_RUN + "-A1"


def _signal(signal_id="SIG-20260817-legacy", *, route="api/COL-PUBMED", source="SRC-040"):
    return {
        "signal_id": signal_id,
        "run_key": RUN,
        "collection_batch_id": "COL-20260817-1910-BJT-COL-PUBMED",
        "producer_id": "collector/COL-PUBMED",
        "origin_attempt_id": "",
        "discovered_at_bjt": "2026-08-17T19:10:33+08:00",
        "channel_id": "C5",
        "route_id": route,
        "source_id": source,
        "discovery_method": "api",
        "raw_title": "Legacy structured result",
        "raw_snippet": "evidence",
        "published_at_hint": "2026-08-17",
        "url": "https://example.com/legacy/1",
        "stable_id": "LEGACY:1",
        "signal_key": "sha256:legacy",
        "priority_hint": "P1",
        "ai_core_hint": "TRUE",
        "life_science_core_hint": "TRUE",
        "signal_state": "active",
        "schema_version": "v11.0",
    }


def _coverage(*, count=1, route="api/COL-PUBMED", source="SRC-040"):
    return {
        "run_key": RUN,
        "source_id": source,
        "source_name": "PubMed",
        "source_group": "structured",
        "route": "api",
        "status": "ok",
        "hit_count": count,
        "checked_at_bjt": "2026-08-17T19:11:00+08:00",
        "fallback_used": "FALSE",
        "retrieval_status": "complete",
        "hit_status": "hit" if count else "no_hit",
        "coverage_id": "sha256:legacy-coverage",
        "attempt_id": "",
        "producer_id": "collector/COL-PUBMED",
        "channel_id": "C5",
        "route_id": route,
        "execution_status": "complete",
        "saturation_status": "clear",
        "results_seen": count,
        "relevant_signal_count": count,
        "schema_version": "v11.0",
    }


def _qualify(signals, coverage, *, attempts=(ATTEMPT,), fingerprint=None):
    persisted = fingerprint or legacy_structured_snapshot_fingerprint(
        run_key=RUN,
        active_signals=signals,
        coverage_rows=coverage,
    )
    return qualify_legacy_frozen_structured_snapshot(
        source_run_key=RUN,
        source_attempt_id=ATTEMPT,
        source_attempt_ids=attempts,
        active_signals=signals,
        coverage_rows=coverage,
        expected_persisted_fingerprint=persisted,
    )


def test_legacy_adapter_qualifies_in_memory_without_mutating_history():
    signal = _signal()
    coverage = _coverage()
    qualified = _qualify([signal], [coverage])

    assert signal["origin_attempt_id"] == ""
    assert coverage["attempt_id"] == ""
    assert qualified.active_signals[0]["origin_attempt_id"] == ATTEMPT
    assert qualified.coverage_rows[0]["attempt_id"] == ATTEMPT
    assert qualified.persisted_fingerprint.startswith("sha256:")
    assert qualified.qualified_fingerprint.startswith("sha256:")


def test_qualified_legacy_snapshot_passes_unchanged_strict_frozen_validator():
    signal = _signal()
    coverage = _coverage()
    qualified = _qualify([signal], [coverage])

    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=list(qualified.active_signals),
        candidates=[{"source_signal_ids": signal["signal_id"]}],
        coverage_rows=list(qualified.coverage_rows),
        required_routes={},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=qualified.qualified_fingerprint,
    )
    assert errors == []


def test_legacy_adapter_requires_exactly_one_matching_durable_source_attempt():
    with pytest.raises(ValueError, match="legacy_frozen_source_attempt_not_unique"):
        _qualify([_signal()], [_coverage()], attempts=(ATTEMPT, RUN + "-A2"))


def test_legacy_adapter_rejects_mixed_signal_attempt_provenance():
    signal = _signal()
    signal["origin_attempt_id"] = RUN + "-A2"
    with pytest.raises(ValueError, match="legacy_frozen_signal_provenance_not_uniformly_blank"):
        _qualify([signal], [_coverage()])


def test_legacy_adapter_rejects_mixed_coverage_attempt_provenance():
    coverage = _coverage()
    coverage["attempt_id"] = RUN + "-A2"
    with pytest.raises(ValueError, match="legacy_frozen_coverage_provenance_not_uniformly_blank"):
        _qualify([_signal()], [coverage])


def test_legacy_adapter_rejects_route_level_signal_count_mismatch():
    with pytest.raises(ValueError, match="legacy_frozen_route_signal_count_mismatch"):
        _qualify([_signal()], [_coverage(count=2)])


def test_legacy_adapter_rejects_persisted_fingerprint_drift():
    with pytest.raises(ValueError, match="legacy_frozen_persisted_fingerprint_mismatch"):
        _qualify([_signal()], [_coverage()], fingerprint="sha256:not-live")


def test_legacy_adapter_does_not_import_source_worker_signal():
    structured = _signal()
    source_worker = build_worker_signal(
        run_key=RUN,
        attempt_id=ATTEMPT,
        batch_id="OLD-WORKER",
        producer_id="chatgpt/worker",
        discovered_at_bjt="2026-08-17T20:40:00+08:00",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        discovery_method="web_search",
        title="Source-run Worker result",
        snippet="must not be inherited",
        url="https://example.com/source-worker",
        published_at="2026-08-17",
    ).values
    qualified = _qualify([structured, source_worker], [_coverage()])

    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=list(qualified.active_signals),
        candidates=[{"source_signal_ids": source_worker["signal_id"]}],
        coverage_rows=list(qualified.coverage_rows),
        required_routes={},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=qualified.qualified_fingerprint,
    )
    assert errors == ["candidate_references_nonactive_signal"]


def test_manual_candidate_can_combine_qualified_legacy_and_current_worker_signal():
    structured = _signal()
    structured_coverage = _coverage()
    qualified = _qualify([structured], [structured_coverage])
    worker = build_worker_signal(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        batch_id="NEW-WORKER",
        producer_id="chatgpt/worker",
        discovered_at_bjt="2026-08-17T23:20:00+08:00",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        discovery_method="web_search",
        title="Current manual Worker result",
        snippet="current evidence",
        url="https://example.com/current-worker",
        published_at="2026-08-17",
    ).values
    worker_coverage = build_worker_coverage(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        producer_id="chatgpt/worker",
        channel_id="C1",
        route_id="worker/c1/broad/01",
        source_id="SRC-X",
        execution_status="complete",
        checked_at_bjt="2026-08-17T23:21:00+08:00",
        relevant_signal_count=1,
    ).values

    errors = validate_unified_ingestion_snapshot(
        run_key=MANUAL_RUN,
        attempt_id=MANUAL_ATTEMPT,
        active_signals=list(qualified.active_signals) + [worker],
        candidates=[{"source_signal_ids": [structured["signal_id"], worker["signal_id"]]}],
        coverage_rows=list(qualified.coverage_rows) + [worker_coverage],
        required_routes={"C1": {"worker/c1/broad/01"}},
        frozen_structured_run_key=RUN,
        frozen_structured_attempt_id=ATTEMPT,
        frozen_structured_fingerprint=qualified.qualified_fingerprint,
    )
    assert errors == []
