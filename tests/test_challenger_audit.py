from ails_intel.challenger_audit import (
    make_challenger_id,
    summarize_confirmed_misses,
    validate_challenger_audit_snapshot,
    validate_challenger_row,
)


def row(**overrides):
    base = {
        "report_date": "2026-08-13",
        "run_key": "AILS11S-20260813-2030-BJT",
        "audit_attempt_id": "AILS11S-20260813-2030-BJT-CH1",
        "provider_id": "external-tool-a",
        "received_at_bjt": "2026-08-13T21:45:00+08:00",
        "raw_title": "Example life-science financing event",
        "raw_url": "https://example.com/news/item",
        "raw_summary": "External challenger claim.",
        "claimed_source_published_at": "2026-08-12",
        "claimed_event_date": "2026-08-12",
        "entity_hint": "Example Biotech",
        "event_type_hint": "financing",
        "content_class_hint": "hard_event",
        "matched_signal_ids": "",
        "matched_candidate_ids": "",
        "matched_event_key": "",
        "disposition": "confirmed_miss",
        "miss_type": "discovery_miss",
        "miss_severity": "material",
        "primary_source_status": "verified",
        "canonical_primary_url": "https://example.com/company/news",
        "source_published_at": "2026-08-12",
        "first_public_at": "2026-08-12",
        "event_date": "2026-08-12",
        "audited_at_bjt": "2026-08-13T22:00:00+08:00",
        "notes": "primary source verified",
        "schema_version": "v11.2",
    }
    base.update(overrides)
    base["challenger_id"] = make_challenger_id(
        base["report_date"], base["provider_id"], base["raw_url"], base["raw_title"]
    )
    return base


def test_challenger_id_is_deterministic_and_ignores_url_fragment():
    one = make_challenger_id(
        "2026-08-13", "Tool-A", "https://Example.com/a/#section", "  Example   Event "
    )
    two = make_challenger_id(
        "2026-08-13", "tool-a", "https://example.com/a", "example event"
    )
    assert one == two


def test_confirmed_miss_requires_primary_and_time_provenance():
    invalid = row(primary_source_status="unverified", canonical_primary_url="", first_public_at="", event_date="")
    errors = validate_challenger_row(invalid, window_start="2026-08-12", window_end="2026-08-13")
    assert "confirmed_miss_primary_not_verified" in errors
    assert "confirmed_miss_missing_primary_url" in errors
    assert "confirmed_miss_missing_time_provenance" in errors


def test_confirmed_miss_must_have_been_inside_target_window():
    invalid = row(first_public_at="2026-07-01", event_date="2026-07-01")
    errors = validate_challenger_row(invalid, window_start="2026-08-12", window_end="2026-08-13")
    assert "confirmed_miss_outside_window" in errors


def test_stale_resurfacing_is_not_a_miss():
    stale = row(
        disposition="stale_resurfacing",
        miss_type="",
        miss_severity="",
        primary_source_status="verified",
        source_published_at="2026-08-12",
        first_public_at="2026-07-06",
        event_date="2026-07-06",
    )
    assert validate_challenger_row(stale) == []
    summary = summarize_confirmed_misses([stale])
    assert summary.confirmed_misses == 0


def test_duplicate_known_event_requires_event_key():
    duplicate = row(
        disposition="duplicate_known_event",
        miss_type="",
        miss_severity="",
        primary_source_status="verified",
        matched_event_key="",
    )
    assert "duplicate_known_event_missing_event_key" in validate_challenger_row(duplicate)


def test_evidence_insufficient_cannot_be_marked_primary_verified():
    unresolved = row(
        disposition="evidence_insufficient",
        miss_type="",
        miss_severity="",
        primary_source_status="verified",
    )
    assert "evidence_insufficient_marked_verified" in validate_challenger_row(unresolved)


def test_snapshot_is_idempotent_and_reconciles_run_counts():
    critical = row(raw_title="Critical miss", raw_url="https://example.com/critical", miss_severity="critical")
    material = row(raw_title="Material miss", raw_url="https://example.com/material", miss_severity="material")
    scope = row(
        raw_title="Out of scope",
        raw_url="https://example.com/math",
        disposition="scope_mismatch",
        miss_type="",
        miss_severity="",
        primary_source_status="not_required",
        canonical_primary_url="",
        first_public_at="",
        event_date="",
    )
    run_row = {"confirmed_misses": "2", "critical_misses": "1", "material_misses": "1"}
    assert validate_challenger_audit_snapshot(
        rows=[critical, material, scope],
        report_date="2026-08-13",
        run_key="AILS11S-20260813-2030-BJT",
        window_start="2026-08-12",
        window_end="2026-08-13",
        run_row=run_row,
    ) == []

    errors = validate_challenger_audit_snapshot(
        rows=[critical, critical],
        report_date="2026-08-13",
        run_key="AILS11S-20260813-2030-BJT",
    )
    assert "duplicate_challenger_id" in errors


def test_run_count_mismatch_is_detected():
    miss = row()
    errors = validate_challenger_audit_snapshot(
        rows=[miss],
        report_date="2026-08-13",
        run_key="AILS11S-20260813-2030-BJT",
        run_row={"confirmed_misses": 0, "critical_misses": 0, "material_misses": 0},
    )
    assert "challenger_run_confirmed_misses_mismatch" in errors
    assert "challenger_run_material_misses_mismatch" in errors
