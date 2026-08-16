from ails_intel.challenger_audit import (
    make_audit_revision_id,
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
        "notes": "verification evidence checked",
        "schema_version": "v11.3",
        "direct_url_status": "inspected",
        "entity_resolution_status": "resolved",
        "event_truth_status": "confirmed",
        "freshness_status": "confirmed_fresh",
        "detail_verification_status": "verified",
        "verification_confidence": "high",
        "contradiction_evidence": "",
        "audit_revision_id": "",
        "supersedes_revision_id": "",
        "audit_state": "current",
    }
    base.update(overrides)
    base["challenger_id"] = str(base.get("challenger_id") or make_challenger_id(
        base["report_date"], base["provider_id"], base["raw_url"], base["raw_title"]
    ))
    if not base.get("audit_revision_id"):
        base["audit_revision_id"] = make_audit_revision_id(base["challenger_id"], 1)
    return base


def test_challenger_id_is_deterministic_and_ignores_url_fragment():
    one = make_challenger_id(
        "2026-08-13", "Tool-A", "https://Example.com/a/#section", "  Example   Event "
    )
    two = make_challenger_id(
        "2026-08-13", "tool-a", "https://example.com/a", "example event"
    )
    assert one == two


def test_confirmed_miss_requires_evidence_and_time_provenance():
    invalid = row(primary_source_status="not_found", canonical_primary_url="", first_public_at="", event_date="")
    errors = validate_challenger_row(invalid, window_start="2026-08-12", window_end="2026-08-13")
    assert "confirmed_miss_evidence_not_verified_or_attributed" in errors
    assert "confirmed_miss_missing_evidence_url" in errors
    assert "confirmed_miss_missing_time_provenance" in errors


def test_confirmed_miss_may_use_attributed_media_when_primary_is_unverified():
    attributed = row(primary_source_status="unverified")
    assert validate_challenger_row(attributed) == []


def test_confirmed_miss_must_have_been_inside_target_window():
    invalid = row(first_public_at="2026-07-01", event_date="2026-07-01")
    errors = validate_challenger_row(invalid, window_start="2026-08-12", window_end="2026-08-13")
    assert "confirmed_miss_outside_window" in errors


def test_direct_url_must_be_inspected_before_final_verdict():
    invalid = row(direct_url_status="not_provided")
    assert "challenger_raw_url_not_inspected_first" in validate_challenger_row(invalid)


def test_no_raw_url_uses_not_provided_state():
    valid = row(raw_url="", direct_url_status="not_provided")
    assert validate_challenger_row(valid) == []


def test_false_claim_requires_resolved_entity_and_explicit_contradiction():
    invalid = row(
        disposition="false_or_inaccurate_claim",
        miss_type="",
        miss_severity="",
        entity_resolution_status="unresolved",
        event_truth_status="unresolved",
        freshness_status="unresolved",
        detail_verification_status="unresolved",
        contradiction_evidence="",
    )
    errors = validate_challenger_row(invalid)
    assert "false_claim_entity_not_resolved" in errors
    assert "false_claim_missing_contradiction_evidence" in errors
    assert "false_claim_without_contradicted_dimension" in errors

    valid = row(
        disposition="false_or_inaccurate_claim",
        miss_type="",
        miss_severity="",
        entity_resolution_status="resolved",
        event_truth_status="confirmed",
        freshness_status="contradicted",
        detail_verification_status="verified",
        contradiction_evidence="Official filing explicitly says the transaction remains pending.",
    )
    assert validate_challenger_row(valid) == []


def test_verified_source_can_still_be_evidence_insufficient_on_freshness_or_details():
    unresolved = row(
        disposition="evidence_insufficient",
        miss_type="",
        miss_severity="",
        primary_source_status="verified",
        event_truth_status="confirmed",
        freshness_status="unresolved",
        detail_verification_status="partial",
        verification_confidence="medium",
    )
    assert validate_challenger_row(unresolved) == []


def test_entity_ambiguity_cannot_be_promoted_to_false_claim_by_absence_of_evidence():
    unresolved = row(
        disposition="evidence_insufficient",
        miss_type="",
        miss_severity="",
        primary_source_status="not_found",
        entity_resolution_status="ambiguous",
        event_truth_status="unresolved",
        freshness_status="unresolved",
        detail_verification_status="unresolved",
        verification_confidence="low",
    )
    assert validate_challenger_row(unresolved) == []


def test_stale_resurfacing_is_not_a_miss():
    stale = row(
        disposition="stale_resurfacing",
        miss_type="",
        miss_severity="",
        primary_source_status="verified",
        source_published_at="2026-08-12",
        first_public_at="2026-07-06",
        event_date="2026-07-06",
        freshness_status="stale",
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


def test_append_only_revisions_allow_same_challenger_with_one_current_revision():
    first = row(audit_state="superseded")
    second = row(
        challenger_id=first["challenger_id"],
        audit_revision_id=make_audit_revision_id(first["challenger_id"], 2),
        supersedes_revision_id=first["audit_revision_id"],
        audit_state="current",
    )
    assert validate_challenger_audit_snapshot(
        rows=[first, second],
        report_date="2026-08-13",
        run_key="AILS11S-20260813-2030-BJT",
    ) == []


def test_duplicate_revision_id_is_rejected():
    first = row(audit_state="superseded")
    second = row(challenger_id=first["challenger_id"], audit_revision_id=first["audit_revision_id"])
    errors = validate_challenger_audit_snapshot(
        rows=[first, second],
        report_date="2026-08-13",
        run_key="AILS11S-20260813-2030-BJT",
    )
    assert "duplicate_challenger_audit_revision_id" in errors


def test_snapshot_reconciles_run_counts_using_current_revisions_only():
    critical = row(raw_title="Critical miss", raw_url="https://example.com/critical", miss_severity="critical")
    material = row(raw_title="Material miss", raw_url="https://example.com/material", miss_severity="material")
    old_material = dict(material)
    old_material["audit_revision_id"] = make_audit_revision_id(material["challenger_id"], 1)
    old_material["audit_state"] = "superseded"
    material["audit_revision_id"] = make_audit_revision_id(material["challenger_id"], 2)
    material["supersedes_revision_id"] = old_material["audit_revision_id"]
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
        entity_resolution_status="not_required",
        event_truth_status="not_applicable",
        freshness_status="not_applicable",
        detail_verification_status="not_applicable",
        verification_confidence="high",
    )
    run_row = {"confirmed_misses": "2", "critical_misses": "1", "material_misses": "1"}
    assert validate_challenger_audit_snapshot(
        rows=[critical, old_material, material, scope],
        report_date="2026-08-13",
        run_key="AILS11S-20260813-2030-BJT",
        window_start="2026-08-12",
        window_end="2026-08-13",
        run_row=run_row,
    ) == []


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
