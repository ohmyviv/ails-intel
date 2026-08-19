from ails_intel.worker_checkpoint import (
    SEALED_G2_MATERIALIZATION_NOTE,
    build_g2_route_handoff,
)

RUN = "AILS11M-20260818-0744-BJT"
ATTEMPT = RUN + "-A3"


def _summary(channel: str, route_id: str, **overrides):
    row = {
        "run_key": RUN,
        "attempt_id": ATTEMPT,
        "producer_id": "chatgpt/worker",
        "row_type": "route_summary",
        "channel_id": channel,
        "route_id": route_id,
        "notes": SEALED_G2_MATERIALIZATION_NOTE,
    }
    row.update(overrides)
    return row


def _handoff(base, audits, due=(), *, legacy=False):
    return build_g2_route_handoff(
        run_key=RUN,
        attempt_id=ATTEMPT,
        base_required_routes=base,
        due_source_route_ids=due,
        audit_rows=audits,
        allow_legacy_broad_aliases=legacy,
    )


def test_canonical_route_remains_canonical():
    route = "worker/c1/broad/01"
    result = _handoff({"C1": {route}}, [_summary("C1", route)], legacy=True)
    assert result.errors == ()
    assert result.required_routes == {"C1": {route}}
    assert result.legacy_alias_count == 0


def test_sealed_g2_legacy_broad_alias_can_bridge_historical_checkpoint():
    result = _handoff(
        {"C1": {"worker/c1/broad/01"}},
        [_summary("C1", "worker/broad/1")],
        legacy=True,
    )
    assert result.errors == ()
    assert result.required_routes == {"C1": {"worker/broad/1"}}
    assert result.legacy_alias_count == 1


def test_legacy_broad_alias_is_opt_in_only():
    result = _handoff(
        {"C1": {"worker/c1/broad/01"}},
        [_summary("C1", "worker/broad/1")],
        legacy=False,
    )
    assert result.errors == ()
    assert result.required_routes == {"C1": {"worker/c1/broad/01"}}
    assert result.legacy_alias_count == 0


def test_unsealed_legacy_alias_fails_closed():
    result = _handoff(
        {"C1": {"worker/c1/broad/01"}},
        [_summary("C1", "worker/broad/1", notes="manual_reconstruction")],
        legacy=True,
    )
    assert result.errors == ("g2_handoff_legacy_broad_alias_not_sealed_g2",)
    assert result.required_routes == {"C1": {"worker/c1/broad/01"}}


def test_canonical_and_legacy_alias_collision_fails_closed():
    result = _handoff(
        {"C1": {"worker/c1/broad/01"}},
        [
            _summary("C1", "worker/c1/broad/01"),
            _summary("C1", "worker/broad/1"),
        ],
        legacy=True,
    )
    assert result.errors == ("g2_handoff_legacy_broad_alias_collision",)


def test_due_only_route_extends_required_universe_using_persisted_channel():
    route = "worker/source/SRC-006"
    result = _handoff(
        {"C1": {"worker/plan/E6"}},
        [_summary("C1", "worker/plan/E6"), _summary("C4", route)],
        due={route},
    )
    assert result.errors == ()
    assert result.required_routes["C4"] == {route}
    assert result.due_extension_count == 1


def test_due_route_already_in_base_is_not_double_counted():
    route = "worker/source/SRC-001"
    result = _handoff(
        {"C1": {route}},
        [_summary("C1", route)],
        due={route},
    )
    assert result.errors == ()
    assert result.required_routes == {"C1": {route}}
    assert result.due_extension_count == 0


def test_missing_due_route_summary_fails_closed():
    route = "worker/source/SRC-006"
    result = _handoff({"C1": {"worker/plan/E6"}}, [_summary("C1", "worker/plan/E6")], due={route})
    assert result.errors == ("g2_handoff_due_route_summary_missing",)


def test_due_route_channel_ambiguity_fails_closed():
    route = "worker/source/SRC-006"
    result = _handoff(
        {"C1": {"worker/plan/E6"}},
        [_summary("C4", route), _summary("C6", route)],
        due={route},
    )
    assert result.errors == ("g2_handoff_due_route_channel_ambiguous",)
