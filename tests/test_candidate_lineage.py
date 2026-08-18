from ails_intel.candidate_lineage import validate_candidate_signal_lineage


def _ctgov_signal():
    return {
        "signal_id": "SIG-20260818-a8f868c96c5c",
        "run_key": "AILS11S-20260818-2030-BJT",
        "producer_id": "collector/COL-CTGOV",
        "signal_state": "active",
        "stable_id": "NCT07756398",
        "event_date_hint": "2026-08-17",
        "published_at_hint": "2026-08-17",
        "first_public_at_hint": "2026-08-10",
        "notes": (
            "ctgov_material=material-hash;"
            "ctgov_delta=enrollment_changed;"
            "ctgov_status=NOT_YET_RECRUITING;"
            "ctgov_enrollment=1088;ctgov_results=0"
        ),
    }


def _candidate(**overrides):
    row = {
        "candidate_id": "CAN-20260818-687649692125",
        "source_signal_ids": "SIG-20260818-a8f868c96c5c",
        "first_public_at": "2026-08-10",
        "event_key_v11": "NCT07756398|enrollment_changed|2026-08-17",
        "delta_key": "NCT07756398|enrollment_changed|2026-08-17",
    }
    row.update(overrides)
    return row


def test_ctgov_material_update_cannot_be_recast_as_new_registration():
    errors = validate_candidate_signal_lineage(
        candidates=[
            _candidate(
                event_key_v11="NCT07756398|new_registration|2026-08-17",
                delta_key="NCT07756398|new_registration|2026-08-17",
            )
        ],
        active_signals=[_ctgov_signal()],
    )
    assert errors == [
        "candidate_ctgov_delta_key_mismatch",
        "candidate_ctgov_event_key_mismatch",
    ]


def test_ctgov_material_update_preserves_delta_and_first_public_lineage():
    assert validate_candidate_signal_lineage(
        candidates=[_candidate()],
        active_signals=[_ctgov_signal()],
    ) == []


def test_ctgov_first_public_at_cannot_be_rewritten():
    errors = validate_candidate_signal_lineage(
        candidates=[_candidate(first_public_at="2026-08-17")],
        active_signals=[_ctgov_signal()],
    )
    assert errors == ["candidate_ctgov_first_public_at_mismatch"]
