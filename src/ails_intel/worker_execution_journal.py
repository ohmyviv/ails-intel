from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

EVENT_TYPES = {
    "route_started",
    "search_returned",
    "search_failed",
    "page_opened",
    "result_screened",
    "route_finalized",
    "route_sealed",
}
FINAL_STATUSES = {"complete", "partial", "failed"}
DISPOSITIONS = {"qualified_signal", "rejected"}
COUNT_FIELDS = (
    "results_returned",
    "results_screened",
    "pages_opened",
    "fresh_results",
    "qualifying_results",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _exact_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    text = _text(value)
    if not text or not text.isdigit():
        return None
    return int(text)


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def event_hash(event_without_hash: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(event_without_hash).encode("utf-8")).hexdigest()


def _event_for_hash(event: Mapping[str, object]) -> dict[str, object]:
    return {k: v for k, v in event.items() if k != "event_hash"}


def load_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    journal = Path(path)
    if not journal.exists():
        return []
    events: list[dict[str, Any]] = []
    with journal.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_jsonl:{line_no}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"event_not_object:{line_no}")
            events.append(value)
    return events


class DurableExecutionJournal:
    """Append-only, fsync-backed execution journal with immediate readback.

    The writer deliberately does not expose an update API. Once an execution
    fact is appended it can only be superseded by a later event; historical
    events are immutable evidence.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_and_verify(self, event: Mapping[str, object]) -> dict[str, Any]:
        base = dict(event)
        if "event_hash" in base or "event_seq" in base or "previous_event_hash" in base:
            raise ValueError("caller_must_not_supply_chain_fields")

        existing = load_jsonl(self.path)
        previous_hash = _text(existing[-1].get("event_hash")) if existing else ""
        chained: dict[str, Any] = {
            **base,
            "event_seq": len(existing) + 1,
            "previous_event_hash": previous_hash,
        }
        chained["event_hash"] = event_hash(_event_for_hash(chained))
        serialized = _canonical_json(chained)

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        try:
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

        reread = load_jsonl(self.path)
        if not reread or reread[-1] != chained:
            raise OSError("journal_readback_mismatch")
        return chained


def _route_key(event: Mapping[str, object]) -> tuple[str, str]:
    return (_text(event.get("channel_id")), _text(event.get("route_id")))


def derive_route_summary(events: Iterable[Mapping[str, object]]) -> dict[str, object]:
    route_events = list(events)
    if not route_events:
        raise ValueError("route_events_empty")

    route_keys = {_route_key(event) for event in route_events}
    if len(route_keys) != 1:
        raise ValueError("route_events_mixed_routes")
    channel_id, route_id = next(iter(route_keys))

    search_returned = [event for event in route_events if _text(event.get("event_type")) == "search_returned"]
    search_failed = [event for event in route_events if _text(event.get("event_type")) == "search_failed"]
    finalized = [event for event in route_events if _text(event.get("event_type")) == "route_finalized"]
    sealed = [event for event in route_events if _text(event.get("event_type")) == "route_sealed"]

    if len(finalized) != 1:
        raise ValueError("route_finalized_count_not_one")
    if len(sealed) != 1:
        raise ValueError("route_sealed_count_not_one")
    if _text(route_events[-1].get("event_type")) != "route_sealed":
        raise ValueError("route_not_sealed_last")
    if len(route_events) < 2 or _text(route_events[-2].get("event_type")) != "route_finalized":
        raise ValueError("route_seal_not_immediately_after_finalize")
    status = _text(finalized[0].get("execution_status"))
    if status not in FINAL_STATUSES:
        raise ValueError("route_finalized_status_invalid")

    if len(search_returned) == 1 and not search_failed:
        returned = _exact_nonnegative_int(search_returned[0].get("results_returned"))
        if returned is None:
            raise ValueError("search_returned_count_invalid")
    elif len(search_failed) == 1 and not search_returned:
        returned = 0
    else:
        raise ValueError("search_terminal_event_invalid")

    screened_events = [event for event in route_events if _text(event.get("event_type")) == "result_screened"]
    opened_events = [
        event
        for event in route_events
        if _text(event.get("event_type")) == "page_opened" and event.get("success") is True
    ]

    screened = len(screened_events)
    opened = len(opened_events)
    fresh = sum(1 for event in screened_events if event.get("fresh") is True)
    qualifying = sum(
        1 for event in screened_events if _text(event.get("disposition")) == "qualified_signal"
    )

    summary: dict[str, object] = {
        "channel_id": channel_id,
        "route_id": route_id,
        "execution_status": status,
        "results_returned": returned,
        "results_screened": screened,
        "pages_opened": opened,
        "fresh_results": fresh,
        "qualifying_results": qualifying,
    }
    failure_reason = _text(finalized[0].get("failure_reason")) or (
        _text(search_failed[0].get("failure_reason")) if search_failed else ""
    )
    if failure_reason:
        summary["failure_reason"] = failure_reason
    return summary


def materialize_route_summary(
    events: Iterable[Mapping[str, object]],
    *,
    base_fields: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Create a route-summary row from sealed execution events only.

    Count fields supplied in base_fields are rejected so callers cannot replace
    derived execution facts with model-entered values.
    """
    base = dict(base_fields or {})
    forbidden = set(COUNT_FIELDS) | {"execution_status"}
    if forbidden.intersection(base):
        raise ValueError("base_fields_must_not_override_execution_facts")
    return {**base, **derive_route_summary(events)}


def validate_summary_against_events(
    summary: Mapping[str, object], events: Iterable[Mapping[str, object]]
) -> list[str]:
    errors: list[str] = []
    try:
        derived = derive_route_summary(events)
    except ValueError as exc:
        return [f"execution_journal_unmaterializable:{exc}"]

    for field in ("execution_status", *COUNT_FIELDS):
        actual = summary.get(field)
        expected = derived.get(field)
        if field in COUNT_FIELDS:
            parsed = _exact_nonnegative_int(actual)
            if parsed is None or parsed != expected:
                errors.append(f"execution_fact_mismatch:{field}")
        elif _text(actual) != _text(expected):
            errors.append("execution_fact_mismatch:execution_status")
    return sorted(set(errors))


def validate_worker_execution_journal(
    events: Iterable[Mapping[str, object]],
    *,
    required_routes: Mapping[str, set[str]] | None = None,
) -> list[str]:
    """Validate G2 execution provenance and lifecycle ordering fail-closed."""
    rows = list(events)
    errors: list[str] = []
    if not rows:
        return ["execution_journal_empty"]

    expected_seq = 1
    previous_hash = ""
    run_key = _text(rows[0].get("run_key"))
    attempt_id = _text(rows[0].get("attempt_id"))
    current_route: tuple[str, str] | None = None
    sealed_routes: set[tuple[str, str]] = set()
    per_route: dict[tuple[str, str], list[Mapping[str, object]]] = {}

    for event in rows:
        seq = _exact_nonnegative_int(event.get("event_seq"))
        if seq != expected_seq:
            errors.append("execution_journal_sequence_gap")
        expected_seq += 1

        if _text(event.get("run_key")) != run_key or _text(event.get("attempt_id")) != attempt_id:
            errors.append("execution_journal_attempt_mixed")

        if _text(event.get("previous_event_hash")) != previous_hash:
            errors.append("execution_journal_hash_chain_previous_mismatch")
        stored_hash = _text(event.get("event_hash"))
        calculated_hash = event_hash(_event_for_hash(event))
        if stored_hash != calculated_hash:
            errors.append("execution_journal_hash_mismatch")
        previous_hash = stored_hash

        event_type = _text(event.get("event_type"))
        if event_type not in EVENT_TYPES:
            errors.append("execution_journal_event_type_invalid")
            continue

        key = _route_key(event)
        if not all(key):
            errors.append("execution_journal_route_identity_missing")
            continue
        per_route.setdefault(key, []).append(event)

        if event_type == "route_started":
            if current_route is not None:
                errors.append("execution_journal_route_interleaving")
            if key in sealed_routes:
                errors.append("execution_journal_route_restarted_after_seal")
            current_route = key
            continue

        if current_route != key:
            errors.append("execution_journal_event_outside_active_route")

        route_events = per_route[key]
        prior_types = [_text(row.get("event_type")) for row in route_events[:-1]]

        if event_type in {"search_returned", "search_failed"}:
            if "route_started" not in prior_types:
                errors.append("execution_journal_search_before_route_start")
            if any(kind in {"search_returned", "search_failed"} for kind in prior_types):
                errors.append("execution_journal_search_terminal_duplicate")
            if event_type == "search_returned":
                returned = _exact_nonnegative_int(event.get("results_returned"))
                if returned is None:
                    errors.append("execution_journal_results_returned_invalid")

        elif event_type == "page_opened":
            if "search_returned" not in prior_types:
                errors.append("execution_event_order_violation:page_open_before_search_journal")
            if event.get("success") not in {True, False}:
                errors.append("execution_journal_page_open_success_invalid")

        elif event_type == "result_screened":
            if "search_returned" not in prior_types:
                errors.append("execution_event_order_violation:screen_before_search_journal")
            if event.get("fresh") not in {True, False}:
                errors.append("execution_journal_fresh_flag_invalid")
            if _text(event.get("disposition")) not in DISPOSITIONS:
                errors.append("execution_journal_disposition_invalid")
            if _text(event.get("disposition")) == "rejected" and not _text(event.get("reject_reason")):
                errors.append("execution_journal_reject_reason_missing")

        elif event_type == "route_finalized":
            if not any(kind in {"search_returned", "search_failed"} for kind in prior_types):
                errors.append("execution_journal_finalize_before_search_terminal")
            if _text(event.get("execution_status")) not in FINAL_STATUSES:
                errors.append("execution_journal_final_status_invalid")
            if any(field in event for field in COUNT_FIELDS):
                errors.append("execution_journal_manual_count_in_finalized_event")
            if "search_failed" in prior_types and _text(event.get("execution_status")) == "complete":
                errors.append("execution_journal_failed_search_marked_complete")

        elif event_type == "route_sealed":
            if not prior_types or prior_types[-1] != "route_finalized":
                errors.append("execution_journal_seal_not_immediately_after_finalize")
            sealed_routes.add(key)
            current_route = None

    if current_route is not None:
        errors.append("execution_journal_unsealed_route")

    for key, route_events in per_route.items():
        types = [_text(event.get("event_type")) for event in route_events]
        if types.count("route_started") != 1:
            errors.append("execution_journal_route_started_count_not_one")
        if types.count("route_finalized") != 1:
            errors.append("execution_journal_route_finalized_count_not_one")
        if types.count("route_sealed") != 1:
            errors.append("execution_journal_route_sealed_count_not_one")

        search_count = types.count("search_returned") + types.count("search_failed")
        if search_count != 1:
            errors.append("execution_journal_search_terminal_count_not_one")

        returned = 0
        search_rows = [event for event in route_events if _text(event.get("event_type")) == "search_returned"]
        if search_rows:
            parsed = _exact_nonnegative_int(search_rows[0].get("results_returned"))
            if parsed is not None:
                returned = parsed

        screened_ranks: set[int] = set()
        opened_ranks: set[int] = set()
        for event in route_events:
            kind = _text(event.get("event_type"))
            if kind not in {"result_screened", "page_opened"}:
                continue
            rank = _exact_nonnegative_int(event.get("result_rank"))
            if rank is None or rank < 1 or rank > returned:
                errors.append("execution_journal_result_rank_invalid")
                continue
            target = screened_ranks if kind == "result_screened" else opened_ranks
            if rank in target:
                errors.append(
                    "execution_journal_duplicate_screened_result"
                    if kind == "result_screened"
                    else "execution_journal_duplicate_page_open"
                )
            target.add(rank)

        try:
            summary = derive_route_summary(route_events)
        except ValueError as exc:
            errors.append(f"execution_journal_unmaterializable:{exc}")
            continue

        if summary["results_screened"] > summary["results_returned"]:
            errors.append("execution_journal_screened_exceeds_returned")
        if summary["fresh_results"] > summary["results_screened"]:
            errors.append("execution_journal_fresh_exceeds_screened")
        if summary["qualifying_results"] > summary["results_screened"]:
            errors.append("execution_journal_qualifying_exceeds_screened")

        if summary["execution_status"] == "complete" and summary["results_returned"] == 0:
            if any(summary[field] for field in COUNT_FIELDS[1:]):
                errors.append("execution_journal_true_zero_inconsistent")

    if required_routes is not None:
        expected_routes = {
            (str(channel).strip(), str(route_id).strip())
            for channel, routes in required_routes.items()
            for route_id in routes
            if str(channel).strip() and str(route_id).strip()
        }
        actual_routes = set(per_route)
        if expected_routes - actual_routes:
            errors.append("execution_journal_required_route_missing")
        if actual_routes - expected_routes:
            errors.append("execution_journal_orphan_route")

    return sorted(set(errors))
