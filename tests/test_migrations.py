from ails_intel.challenger_audit import (
    CHALLENGER_DISPOSITIONS,
    CHALLENGER_HEADERS,
    MISS_SEVERITIES,
    MISS_TYPES,
    PRIMARY_SOURCE_STATUSES,
)
from ails_intel.migrations import MIGRATIONS, sprint_4_6_a1
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
