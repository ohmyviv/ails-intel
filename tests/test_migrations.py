from ails_intel.challenger_audit import (
    CHALLENGER_DISPOSITIONS,
    CHALLENGER_HEADERS,
    MISS_SEVERITIES,
    MISS_TYPES,
    PRIMARY_SOURCE_STATUSES,
)
from ails_intel.migrations import MIGRATIONS, sprint_4_6_a1


def test_sprint_4_6_a1_contract():
    spec = sprint_4_6_a1()
    assert spec.migration_id == "sprint_4_6_a1"
    assert MIGRATIONS[spec.migration_id] is sprint_4_6_a1

    assert len(spec.sheets) == 1
    sheet = spec.sheets[0]
    assert sheet.title == "Lite_ChallengerAudit"
    assert sheet.headers == tuple(CHALLENGER_HEADERS)
    assert sheet.row_count == 3000

    rules = {
        sheet.headers[rule.column_index]: set(rule.values)
        for rule in sheet.validations
    }
    assert rules == {
        "disposition": CHALLENGER_DISPOSITIONS,
        "miss_type": MISS_TYPES,
        "miss_severity": MISS_SEVERITIES,
        "primary_source_status": PRIMARY_SOURCE_STATUSES,
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
