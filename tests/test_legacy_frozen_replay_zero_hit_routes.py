import pytest

from ails_intel.legacy_frozen_replay import (
    legacy_structured_snapshot_fingerprint,
    qualify_legacy_frozen_structured_snapshot,
)

RUN = "AILS11S-20260818-2030-BJT"
ATTEMPT = RUN + "-A1"


def _signal(
    *,
    signal_id: str,
    signal_key: str,
    producer_id: str,
    channel_id: str,
    route_id: str,
    source_id: str,
):
    return {
        "signal_id": signal_id,
        "run_key": RUN,
        "collection_batch_id": "COL-20260818-1909-BJT",
        "producer_id": producer_id,
        "origin_attempt_id": "",
        "discovered_at_bjt": "2026-08-18T19:09:49+08:00",
        "channel_id": channel_id,
        "route_id": route_id,
        "source_id": source_id,
        "discovery_method": "api",
        "raw_title": "Legacy structured result",
        "raw_snippet": "evidence",
        "published_at_hint": "2026-08-18",
        "url": f"https://example.com/{signal_id}",
        "stable_id": signal_id,
        "signal_key": signal_key,
        "priority_hint": "P1",
        "ai_core_hint": "TRUE",
        "life_science_core_hint": "TRUE",
        "signal_state": "active",
        "schema_version": "v11.0",
    }


def _coverage(
    *,
    producer_id: str,
    channel_id: str,
    route_id: str,
    source_id: str,
    count: int,
):
    return {
        "run_key": RUN,
        "source_id": source_id,
        "source_name": source_id,
        "source_group": "structured",
        "route": "api" if route_id.startswith("api/") else "rss",
        "status": "ok",
        "hit_count": count,
        "checked_at_bjt": "2026-08-18T19:09:49+08:00",
        "fallback_used": "FALSE",
        "retrieval_status": "complete",
        "hit_status": "hit" if count else "no_hit",
        "coverage_id": f"sha256:{producer_id}:{route_id}:{source_id}",
        "attempt_id": "",
        "producer_id": producer_id,
        "channel_id": channel_id,
        "route_id": route_id,
        "execution_status": "complete",
        "saturation_status": "clear",
        "results_seen": count,
        "relevant_signal_count": count,
        "schema_version": "v11.0",
    }


def _qualify(signals, coverage):
    fingerprint = legacy_structured_snapshot_fingerprint(
        run_key=RUN,
        active_signals=signals,
        coverage_rows=coverage,
    )
    return qualify_legacy_frozen_structured_snapshot(
        source_run_key=RUN,
        source_attempt_id=ATTEMPT,
        source_attempt_ids=[ATTEMPT],
        active_signals=signals,
        coverage_rows=coverage,
        expected_persisted_fingerprint=fingerprint,
    )


def test_legacy_adapter_accepts_mixed_positive_and_zero_hit_routes():
    pubmed = _signal(
        signal_id="SIG-20260818-pubmed",
        signal_key="sha256:pubmed",
        producer_id="collector/COL-PUBMED",
        channel_id="C5",
        route_id="api/COL-PUBMED",
        source_id="SRC-040",
    )
    coverage = [
        _coverage(
            producer_id="collector/COL-PUBMED",
            channel_id="C5",
            route_id="api/COL-PUBMED",
            source_id="SRC-040",
            count=1,
        ),
        _coverage(
            producer_id="collector/COL-FIERCE-RSS",
            channel_id="C1",
            route_id="rss/COL-FIERCE-RSS",
            source_id="SRC-002",
            count=0,
        ),
    ]

    qualified = _qualify([pubmed], coverage)

    assert len(qualified.active_signals) == 1
    assert len(qualified.coverage_rows) == 2
    assert qualified.active_signals[0]["origin_attempt_id"] == ATTEMPT
    assert {row["attempt_id"] for row in qualified.coverage_rows} == {ATTEMPT}


def test_zero_default_does_not_hide_orphan_positive_signal_route():
    pubmed = _signal(
        signal_id="SIG-20260818-pubmed",
        signal_key="sha256:pubmed",
        producer_id="collector/COL-PUBMED",
        channel_id="C5",
        route_id="api/COL-PUBMED",
        source_id="SRC-040",
    )
    arxiv = _signal(
        signal_id="SIG-20260818-arxiv",
        signal_key="sha256:arxiv",
        producer_id="collector/COL-ARXIV",
        channel_id="C5",
        route_id="api/COL-ARXIV",
        source_id="SRC-018",
    )
    coverage = [
        _coverage(
            producer_id="collector/COL-PUBMED",
            channel_id="C5",
            route_id="api/COL-PUBMED",
            source_id="SRC-040",
            count=1,
        ),
        _coverage(
            producer_id="collector/COL-FIERCE-RSS",
            channel_id="C1",
            route_id="rss/COL-FIERCE-RSS",
            source_id="SRC-002",
            count=0,
        ),
    ]

    with pytest.raises(ValueError, match="legacy_frozen_route_signal_count_mismatch"):
        _qualify([pubmed, arxiv], coverage)
