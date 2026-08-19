from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

WORKER_PRODUCERS = {"chatgpt/worker", "chatgpt/rescue"}
SEALED_G2_MATERIALIZATION_NOTE = "materialized_from_sealed_g2_journal"
_CANONICAL_C1_BROAD_RE = re.compile(r"^worker/c1/broad/(\d{2})$")


def _text(value: object) -> str:
    return str(value or "").strip()


def _legacy_broad_alias(canonical_route_id: str) -> str:
    match = _CANONICAL_C1_BROAD_RE.match(_text(canonical_route_id))
    if not match:
        return ""
    return f"worker/broad/{int(match.group(1))}"


@dataclass(frozen=True)
class G2RouteHandoff:
    required_routes: dict[str, set[str]]
    errors: tuple[str, ...]
    legacy_alias_count: int
    due_extension_count: int


def build_g2_route_handoff(
    *,
    run_key: str,
    attempt_id: str,
    base_required_routes: Mapping[str, set[str]],
    due_source_route_ids: Iterable[str],
    audit_rows: Iterable[Mapping[str, object]],
    allow_legacy_broad_aliases: bool = False,
) -> G2RouteHandoff:
    """Build the G3 route universe from the accepted G2 execution handoff.

    The normal contract remains the current canonical base route set. Registry-
    derived due source routes are valid same-attempt extensions and are assigned
    to the channel recorded by their persisted route-summary evidence.

    Historical manual checkpoints may opt into one narrowly-scoped compatibility
    rule for pre-canonical C1 broad route IDs. The alias is accepted only when
    the same-attempt route summary is explicitly marked as materialized from the
    sealed G2 execution journal. No persisted row is rewritten.
    """
    required: dict[str, set[str]] = {
        str(channel).strip(): {str(route_id).strip() for route_id in routes if str(route_id).strip()}
        for channel, routes in base_required_routes.items()
        if str(channel).strip()
    }
    errors: list[str] = []

    summaries = [
        row
        for row in audit_rows
        if _text(row.get("run_key")) == run_key
        and _text(row.get("attempt_id")) == attempt_id
        and _text(row.get("producer_id")) in WORKER_PRODUCERS
        and _text(row.get("row_type")) == "route_summary"
    ]
    actual_keys = {
        (_text(row.get("channel_id")), _text(row.get("route_id")))
        for row in summaries
        if _text(row.get("channel_id")) and _text(row.get("route_id"))
    }
    summaries_by_key: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in summaries:
        key = (_text(row.get("channel_id")), _text(row.get("route_id")))
        summaries_by_key.setdefault(key, []).append(row)

    legacy_alias_count = 0
    if allow_legacy_broad_aliases:
        for channel, routes in list(required.items()):
            for canonical_route in list(routes):
                alias = _legacy_broad_alias(canonical_route)
                if not alias:
                    continue
                canonical_key = (channel, canonical_route)
                alias_key = (channel, alias)
                if canonical_key in actual_keys and alias_key in actual_keys:
                    errors.append("g2_handoff_legacy_broad_alias_collision")
                    continue
                if canonical_key in actual_keys or alias_key not in actual_keys:
                    continue
                alias_rows = summaries_by_key.get(alias_key, [])
                if len(alias_rows) != 1:
                    errors.append("g2_handoff_legacy_broad_alias_ambiguous")
                    continue
                if _text(alias_rows[0].get("notes")) != SEALED_G2_MATERIALIZATION_NOTE:
                    errors.append("g2_handoff_legacy_broad_alias_not_sealed_g2")
                    continue
                routes.remove(canonical_route)
                routes.add(alias)
                legacy_alias_count += 1

    due_extension_count = 0
    all_required_route_ids = {route_id for routes in required.values() for route_id in routes}
    for route_id in sorted({_text(value) for value in due_source_route_ids if _text(value)}):
        if route_id in all_required_route_ids:
            continue
        matching_channels = {
            channel
            for channel, persisted_route_id in actual_keys
            if persisted_route_id == route_id and channel
        }
        if not matching_channels:
            errors.append("g2_handoff_due_route_summary_missing")
            continue
        if len(matching_channels) != 1:
            errors.append("g2_handoff_due_route_channel_ambiguous")
            continue
        channel = next(iter(matching_channels))
        required.setdefault(channel, set()).add(route_id)
        all_required_route_ids.add(route_id)
        due_extension_count += 1

    return G2RouteHandoff(
        required_routes=required,
        errors=tuple(sorted(set(errors))),
        legacy_alias_count=legacy_alias_count,
        due_extension_count=due_extension_count,
    )
