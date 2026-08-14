import pytest

from ails_intel.challenger_audit import (
    CHALLENGER_DISPOSITIONS,
    CHALLENGER_HEADERS,
    MISS_SEVERITIES,
    MISS_TYPES,
    PRIMARY_SOURCE_STATUSES,
)
from ails_intel.migrations import (
    MIGRATIONS,
    SEARCH_PLAN_HEADERS,
    sprint_4_6_a1,
    sprint_4_6_b1,
)
from ails_intel.schema_manifest import EXPECTED_HEADERS, VALIDATION_PROBES


def test_sprint_4_6_a1_contract():
    spec = sprint_4_6_a1()
    assert spec.migration_id == "sprint_4_6_a1"
    assert MIGRATIONS[spec.migration_id] is sprint_4_6_a1

    assert len(spec.sheets) == 2
    sheets = {sheet.title: sheet for sheet in spec.sheets}

    challenger = sheets["Lite_ChallengerAudit"]
    assert challenger.headers == tuple(CHALLENGER_HEADERS)
    assert challenger.row_count == 3000

    challenger_rules = {
        challenger.headers[rule.column_index]: set(rule.values)
        for rule in challenger.validations
    }
    assert challenger_rules == {
        "disposition": CHALLENGER_DISPOSITIONS,
        "miss_type": MISS_TYPES,
        "miss_severity": MISS_SEVERITIES,
        "primary_source_status": PRIMARY_SOURCE_STATUSES,
    }

    signals = sheets["Lite_Signals"]
    assert signals.headers == tuple(EXPECTED_HEADERS["Lite_Signals"])
    assert signals.row_count == 5000

    signal_rules = {
        signals.headers[rule.column_index]: set(rule.values)
        for rule in signals.validations
    }
    assert signal_rules == {
        "channel_id": VALIDATION_PROBES["Lite_Signals!G2"],
        "discovery_method": VALIDATION_PROBES["Lite_Signals!J2"],
        "priority_hint": VALIDATION_PROBES["Lite_Signals!W2"],
        "ai_core_hint": VALIDATION_PROBES["Lite_Signals!X2"],
        "life_science_core_hint": VALIDATION_PROBES["Lite_Signals!Y2"],
        "signal_state": VALIDATION_PROBES["Lite_Signals!Z2"],
    }

    configs = {item.key: item for item in spec.config_upserts}
    assert set(configs) == {
        "challenger_audit_enabled",
        "challenger_audit_blocking",
        "challenger_disposition_enum",
        "challenger_primary_source_status_enum",
        "challenger_schema_version",
    }
    assert configs["challenger_audit_enabled"].value == "TRUE"
    assert configs["challenger_audit_blocking"].value == "FALSE"
    assert configs["challenger_schema_version"].value == "v11.2"
    assert set(configs["challenger_disposition_enum"].value.split("|")) == CHALLENGER_DISPOSITIONS
    assert set(configs["challenger_primary_source_status_enum"].value.split("|")) == PRIMARY_SOURCE_STATUSES


def _synthetic_plan(plan_id: str, marker: str) -> dict[str, str]:
    return {
        "plan_id": plan_id,
        "lane": "synthetic hard event recall",
        "region": "Global",
        "language": "EN",
        "priority": "P0",
        "query_template": f"(synthetic {marker}) (event action)",
        "cadence": "daily",
        "notes": "synthetic test payload only",
        "status": "active",
        "source_scope": "synthetic",
        "event_types": marker,
        "time_window": "T/T-1",
        "exclusion_terms": "synthetic exclusion",
        "first_seen_only": "TRUE",
        "last_reviewed": "2099-01-01",
        "version": "synthetic-v1",
    }


def test_sprint_4_6_b1_contract_uses_private_payload():
    payload = {
        "search_plans": [
            _synthetic_plan("SYN-HR-1", "financing"),
            _synthetic_plan("SYN-HR-2", "development"),
            _synthetic_plan("SYN-HR-3", "regulatory"),
        ],
        "worker_channel_plan_map_additions": {
            "C1": ["SYN-HR-1", "SYN-HR-2", "SYN-HR-3"],
        },
    }
    spec = sprint_4_6_b1(payload)

    assert spec.migration_id == "sprint_4_6_b1"
    assert MIGRATIONS[spec.migration_id] is sprint_4_6_b1
    assert spec.sheets == ()
    assert spec.config_upserts == ()
    assert len(spec.registry_rows) == 3
    assert all(row.sheet_name == "SearchPlans" for row in spec.registry_rows)
    assert all(row.headers == SEARCH_PLAN_HEADERS for row in spec.registry_rows)
    assert all(row.key_column == "plan_id" for row in spec.registry_rows)

    plan_id_index = SEARCH_PLAN_HEADERS.index("plan_id")
    query_index = SEARCH_PLAN_HEADERS.index("query_template")
    assert [row.values[plan_id_index] for row in spec.registry_rows] == [
        "SYN-HR-1",
        "SYN-HR-2",
        "SYN-HR-3",
    ]
    assert all("synthetic" in row.values[query_index] for row in spec.registry_rows)

    assert len(spec.config_json_map_list_extends) == 1
    extension = spec.config_json_map_list_extends[0]
    assert extension.key == "worker_channel_plan_map_json"
    assert extension.map_key == "C1"
    assert extension.values == ("SYN-HR-1", "SYN-HR-2", "SYN-HR-3")


def test_sprint_4_6_b1_rejects_plan_map_mismatch():
    payload = {
        "search_plans": [
            _synthetic_plan("SYN-HR-1", "financing"),
            _synthetic_plan("SYN-HR-2", "development"),
            _synthetic_plan("SYN-HR-3", "regulatory"),
        ],
        "worker_channel_plan_map_additions": {
            "C1": ["SYN-HR-1", "SYN-HR-2"],
        },
    }
    with pytest.raises(ValueError, match="exactly match"):
        sprint_4_6_b1(payload)


def test_sprint_4_6_b1_requires_private_query_text():
    plans = [
        _synthetic_plan("SYN-HR-1", "financing"),
        _synthetic_plan("SYN-HR-2", "development"),
        _synthetic_plan("SYN-HR-3", "regulatory"),
    ]
    plans[1]["query_template"] = ""
    payload = {
        "search_plans": plans,
        "worker_channel_plan_map_additions": {
            "C1": ["SYN-HR-1", "SYN-HR-2", "SYN-HR-3"],
        },
    }
    with pytest.raises(ValueError, match="requires private query_template"):
        sprint_4_6_b1(payload)
