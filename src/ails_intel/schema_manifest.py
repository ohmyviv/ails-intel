from __future__ import annotations

EXPECTED_HEADERS = {
    "Lite_Config": [
        "config_key","config_value","value_type","active","notes","updated_at_bjt","owner"
    ],
    "Lite_Runs": [
        "run_key","attempt_id","report_date","run_type","started_at_bjt","completed_at_bjt",
        "stage","final_status","fresh_event_count","backfill_count","technical_count","deep_count",
        "candidate_count","verified_count","selected_count","current_event_share","backfill_share",
        "median_event_age_days","source_success_rate","write_status","readback_status","error_stage",
        "error_message","notes","audit_mode","audit_trigger","audit_candidates","confirmed_misses",
        "critical_misses","material_misses","audit_status","audit_notes","retrieval_status",
        "state_status","delivery_status","resume_stage","frozen_item_count",
        "frozen_content_fingerprint","transaction_id","readback_match",
        "canonical_attempt","coverage_confidence_pre_rescue","coverage_confidence",
        "coverage_gate_reason","signal_count","dedup_event_count","p0_signal_count",
        "hard_candidate_count","pending_p0_due_count","mandatory_channels_completed",
        "mandatory_channels_total","channel_health_json","rescue_triggered","rescue_signal_count",
        "rescue_candidate_count","rescue_material_event_count","gap_recovery","gap_days",
        "capture_delay_median_hours","capture_delay_p90_hours","collector_failure_count",
        "collector_saturation_count","signal_baseline","abnormal_low_signal",
        "canonicalized_at_bjt","schema_version"
    ],
    "Lite_EventIndex": [
        "event_key","entity","event_type","content_class","event_date","published_at","first_seen_at",
        "last_seen_at","hard_delta","canonical_title","canonical_url","primary_source","evidence_label",
        "last_reported_run","status","related_event_key","created_at_bjt","updated_at_bjt","notes",
        "legacy_event_id","event_key_v11","latest_delta_key","first_public_at","latest_material_at",
        "last_reported_at","event_status_v11","schema_version"
    ],
    "Lite_Candidates": [
        "candidate_id","run_key","title","entity","event_type","content_class","event_date",
        "published_at","discovery_source","primary_url","supporting_urls","time_lane","evidence_status",
        "novelty_status","score","disposition","rejection_reason","opened_at_bjt","event_key","notes",
        "attempt_id","source_signal_ids","first_public_at","event_key_v11","delta_key","priority_class",
        "materiality_score","evidence_score","novelty_score","investment_relevance_score",
        "independent_route_count","pending_type","missing_evidence","retry_after","expiry_date",
        "last_rechecked_at_bjt","schema_version"
    ],
    "Lite_DailyItems": [
        "run_key","attempt_id","item_index","section","time_lane","event_key","content_class","title",
        "event_date","published_at","summary","new_fact","why_it_matters","investment_view","follow_up",
        "score","evidence_label","primary_url","supporting_urls","primary_source","created_at_bjt","status",
        "age_days","notes","first_public_at","event_key_v11","delta_key","priority_class",
        "capture_delay_hours","schema_version"
    ],
    "Lite_SourceCoverage": [
        "run_key","source_id","source_name","source_group","route","status","hit_count",
        "representative_url","failure_reason","checked_at_bjt","fallback_used","notes",
        "retrieval_status","hit_status","coverage_id","attempt_id","producer_id","channel_id","route_id",
        "execution_status","saturation_status","results_seen","relevant_signal_count","schema_version"
    ],
    "Lite_Signals": [
        "signal_id","run_key","collection_batch_id","producer_id","origin_attempt_id",
        "discovered_at_bjt","channel_id","route_id","source_id","discovery_method","raw_title",
        "raw_snippet","entity_hint","action_hint","asset_hint","event_date_hint","published_at_hint",
        "first_public_at_hint","url","stable_id","signal_key","event_key_hint","priority_hint",
        "ai_core_hint","life_science_core_hint","signal_state","notes","schema_version"
    ],
}

MIN_GRID = {
    "Lite_Signals": {"rowCount": 5000, "columnCount": 28, "frozenRowCount": 1},
}

REQUIRED_V11_CONFIG = {
    "system_version","execution_mode","shadow_run_prefix","production_run_prefix",
    "report_cutoff_hour_bjt","report_cutoff_minute_bjt","schema_version",
    "max_gap_recovery_items","channels_json","mandatory_channels_json",
    "channel_execution_status_enum","channel_hit_status_enum","source_saturation_status_enum",
    "c1_broad_queries_json","c1_premium_sources_json","c1_specialist_sources_json",
    "c1_search_window_hours","c1_required_broad_query_count","entity_event_terms_json",
    "tier_a_daily_required","tier_b_rotation_enabled","structured_collectors_json",
    "collector_retry_limit","collector_timeout_seconds","collector_default_max_results",
    "collector_write_signals_enabled","collector_exact_dedupe_enabled","collector_limits_json",
    "signal_baseline_weeks","signal_baseline_min_runs","signal_floor_ratio","signal_state_enum",
    "signal_priority_enum","signal_max_per_run_soft","verification_slots_hard",
    "verification_slots_technical","verification_slots_deep","verification_slots_rescue",
    "priority_enum","candidate_disposition_enum","pending_enabled","pending_priority_required",
    "pending_default_expiry_days","pending_max_due_per_run","pending_type_enum",
    "score_weight_materiality","score_weight_investment_relevance","score_weight_evidence",
    "score_weight_novelty","coverage_confidence_enum","coverage_gate_enabled",
    "coverage_low_if_c1_failed","coverage_low_if_c2_failed",
    "coverage_low_if_mandatory_degraded_gte","coverage_low_if_gap_unresolved",
    "coverage_medium_if_saturated_sources_gte","coverage_require_premium_sweep",
    "rescue_enabled","rescue_budget_pct","rescue_broad_search_max",
    "rescue_premium_sources_json","rescue_tier_a_exact_sweep","rescue_max_new_candidates",
    "rescue_trigger_on_abnormal_low_signal","rescue_trigger_on_previous_gap",
    "rescue_trigger_on_rolling_critical_miss","shadow_audit_enabled",
    "shadow_audit_weekly_day","shadow_audit_window_days","shadow_audit_budget_pct",
    "miss_type_enum","miss_severity_enum","fingerprint_algorithm",
    "frozen_fingerprint_fields_v11","readback_contract_v11",
}

VALIDATION_PROBES = {
    "Lite_Signals!G2": {"C1","C2","C3","C4","C5","C6"},
    "Lite_Signals!J2": {"api","rss","web","entity","reverse_lookup","official_listing"},
    "Lite_Signals!W2": {"P0","P1","P2"},
    "Lite_Signals!X2": {"TRUE","FALSE","UNKNOWN"},
    "Lite_Signals!Y2": {"TRUE","FALSE","UNKNOWN"},
    "Lite_Signals!Z2": {"active","exact_duplicate","invalid"},
    "Lite_Runs!AP2": {"HIGH","MEDIUM","LOW"},
    "Lite_Runs!AQ2": {"HIGH","MEDIUM","LOW"},
    "Lite_Candidates!P2": {"selected","rejected","pending","expired","superseded"},
    "Lite_Candidates!Z2": {"P0","P1","P2"},
    "Lite_Candidates!AF2": {
        "awaiting_financing_close","awaiting_primary_confirmation","awaiting_clinical_data",
        "awaiting_regulatory_decision","awaiting_deal_terms","awaiting_publication","other"
    },
    "Lite_DailyItems!AB2": {"P0","P1","P2"},
    "Lite_EventIndex!Z2": {"reported","watching","closed","superseded"},
    "Lite_SourceCoverage!T2": {"complete","partial","failed","skipped"},
    "Lite_SourceCoverage!U2": {"clear","saturated","unknown"},
}
