import json

import pytest

from ails_intel.migration_request_runner import extract_private_payload_json, load_request


def test_extract_private_payload_json_accepts_active_json():
    raw = json.dumps({"sprint_4_6_b1": {"search_plans": [], "worker_channel_plan_map_additions": {"C1": []}}})
    rows = [
        ["config_key", "config_value", "value_type", "active", "notes", "updated_at_bjt", "owner"],
        ["private_migration_sprint_4_6_b1_json", raw, "json", "TRUE", "", "", "test"],
    ]
    assert extract_private_payload_json(rows, "sprint_4_6_b1") == raw


def test_extract_private_payload_json_rejects_inactive_or_duplicate():
    raw = json.dumps({"sprint_4_6_b1": {}})
    inactive = [
        ["config_key", "config_value", "value_type", "active", "notes", "updated_at_bjt", "owner"],
        ["private_migration_sprint_4_6_b1_json", raw, "json", "FALSE", "", "", "test"],
    ]
    with pytest.raises(RuntimeError, match="active json"):
        extract_private_payload_json(inactive, "sprint_4_6_b1")

    duplicate = [inactive[0], ["private_migration_sprint_4_6_b1_json", raw, "json", "TRUE"], ["private_migration_sprint_4_6_b1_json", raw, "json", "TRUE"]]
    with pytest.raises(RuntimeError, match="key count"):
        extract_private_payload_json(duplicate, "sprint_4_6_b1")


def test_load_request_contract(tmp_path):
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"request_version": "v1", "migration": "sprint_4_6_b1", "apply": False}),
        encoding="utf-8",
    )
    assert load_request(str(request)) == ("sprint_4_6_b1", False)

    request.write_text(
        json.dumps({"request_version": "v1", "migration": "sprint_4_6_b1", "apply": "false"}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="apply must be boolean"):
        load_request(str(request))
