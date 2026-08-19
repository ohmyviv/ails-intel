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
RESULT_IDENTITY_FIELDS = ("result_title", "result_url", "result_source")
RESULT_ROW_EVIDENCE_FIELDS = (
    "channel_id",
    "route_id",
    "row_type",
    "result_rank",
    "result_title",
    "result_url",
    "result_source",
    "published_at",
    "opened",
    "disposition",
    "reject_reason",
    "signal_id",
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


def _result_rank(event: Mapping[str, object]) -> int:
    rank = _exact_nonnegative_int(event.get("result_rank"))
    if rank is None or rank < 1:
        raise ValueError("result_rank_invalid")
    return rank


def _screened_result_events(events: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    return [event for event in events if _text(event.get("event_type")) == "result_screened"]


def _successful_open_ranks(events: Iterable[Mapping[str, object]]) -> set[int]:
    ranks: set[int] = set()
    for event in events:
        if _text(event.get("event_type")) != "page_opened" or event.get("success") is not True:
            continue
        rank = _exact_nonnegative_int(event.get("result_rank"))
        if rank is not None and rank >= 1:
            ranks.add(rank)
    return ranks


def _result_screened_evidence_errors(event: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    for field in RESULT_IDENTITY_FIELDS:
        if not _text(event.get(field)):
            errors.append(f"execution_journal_{field}_missing")
    disposition = _text(event.get("disposition"))
    if disposition == "qualified_signal" and not _text(event.get("signal_id")):
        errors.append("execution_journal_signal_id_missing")
    return errors


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

    screened_events = _screened_result_events(route_events)
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


def materialize_route_result_rows(
    events: Iterable[Mapping[str, object]],
    *,
    max_result_rows: int = 5,
    base_fields: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Project deterministic WorkerAudit result rows from a sealed route journal.

    All identity and disposition evidence comes from durable ``result_screened``
    events. ``opened`` is derived from successful ``page_opened`` events. The
    deterministic representative order is: qualifying results, then fresh
    results, then successfully opened results, then original result rank.
    """
    if isinstance(max_result_rows, bool) or not isinstance(max_result_rows, int) or max_result_rows < 0:
        raise ValueError("max_result_rows_invalid")

    route_events = list(events)
    summary = derive_route_summary(route_events)
    screened_events = _screened_result_events(route_events)
    evidence_errors = sorted(
        {
            error
            for event in screened_events
            for error in _result_screened_evidence_errors(event)
        }
    )
    if evidence_errors:
        raise ValueError("result_screened_evidence_incomplete:" + ",".join(evidence_errors))

    base = dict(base_fields or {})
    if set(RESULT_ROW_EVIDENCE_FIELDS).intersection(base):
        raise ValueError("base_fields_must_not_override_result_evidence")

    opened_ranks = _successful_open_ranks(route_events)

    def sort_key(event: Mapping[str, object]) -> tuple[int, int, int, int]:
        rank = _result_rank(event)
        return (
            0 if _text(event.get("disposition")) == "qualified_signal" else 1,
            0 if event.get("fresh") is True else 1,
            0 if rank in opened_ranks else 1,
            rank,
        )

    selected = sorted(screened_events, key=sort_key)[:max_result_rows]
    rows: list[dict[str, object]] = []
    for event in selected:
        rank = _result_rank(event)
        disposition = _text(event.get("disposition"))
        row: dict[str, object] = {
            **base,
            "channel_id": summary["channel_id"],
            "route_id": summary["route_id"],
            "row_type": "result",
            "result_rank": rank,
            "result_title": _text(event.get("result_title")),
            "result_url": _text(event.get("result_url")),
            "result_source": _text(event.get("result_source")),
            "published_at": _text(event.get("published_at")),
            "opened": rank in opened_ranks,
            "disposition": disposition,
            "reject_reason": _text(event.get("reject_reason")) if disposition == "rejected" else "",
            "signal_id": _text(event.get("signal_id")) if disposition == "qualified_signal" else "",
        }
        rows.append(row)
    return rows


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


def validate_result_rows_against_events(
    result_rows: Iterable[Mapping[str, object]],
    events: Iterable[Mapping[str, object]],
    *,
    max_result_rows: int = 5,
) -> list[str]:
    """Ensure persisted WorkerAudit result rows equal the journal projection."""
    try:
        expected = materialize_route_result_rows(events, max_result_rows=max_result_rows)
    except ValueError as exc:
        return [f"execution_journal_result_rows_unmaterializable:{exc}"]

    actual = list(result_rows)
    if len(actual) != len(expected):
        return ["worker_audit_result_row_count_mismatch"]

    errors: list[str] = []
    for actual_row, expected_row in zip(actual, expected, strict=True):
        for field in RESULT_ROW_EVIDENCE_FIELDS:
            expected_value = expected_row.get(field)
            actual_value = actual_row.get(field)
            if field == "result_rank":
                if _exact_nonnegative_int(actual_value) != expected_value:
                    errors.append(f"worker_audit_result_evidence_mismatch:{field}")
            elif field == "opened":
                if actual_value is not expected_value:
                    errors.append(f"worker_audit_result_evidence_mismatch:{field}")
            elif _text(actual_value) != _text(expected_value):
                errors.append(f"worker_audit_result_evidence_mismatch:{field}")
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
            disposition = _text(event.get("disposition"))
            if disposition not in DISPOSITIONS:
                errors.append("execution_journal_disposition_invalid")
            if disposition == "rejected" and not _text(event.get("reject_reason")):
                errors.append("execution_journal_reject_reason_missing")
            errors.extend(_result_screened_evidence_errors(event))

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
