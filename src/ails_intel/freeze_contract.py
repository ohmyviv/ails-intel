from __future__ import annotations

from collections.abc import Iterable, Mapping

from ails_intel.fingerprint import frozen_manifest_fingerprint


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _int(value: object, default: int = -1) -> int:
    try:
        return int(float(str(value or "")))
    except (TypeError, ValueError):
        return default


def validate_shadow_freeze_snapshot(
    *,
    run_key: str,
    attempt_id: str,
    candidates: Iterable[Mapping[str, object]],
    daily_items: Iterable[Mapping[str, object]],
    run_rows: Iterable[Mapping[str, object]],
    event_index_rows: Iterable[Mapping[str, object]],
    max_items: int,
) -> list[str]:
    """Validate the Sprint-3C shadow freeze/readback boundary.

    A valid snapshot is committed to Shadow DailyItems with a reproducible
    fingerprint, but remains non-canonical, undelivered, and must not write the
    formal EventIndex. Coverage confidence is carried as metadata and does not
    itself invalidate an otherwise coherent frozen manifest.
    """
    errors: list[str] = []
    candidate_rows = list(candidates)
    items = list(daily_items)
    runs = list(run_rows)
    events = list(event_index_rows)

    selected = {
        str(row.get("delta_key", "")).strip(): row
        for row in candidate_rows
        if str(row.get("disposition", "")).strip() == "selected"
        and str(row.get("delta_key", "")).strip()
    }

    if not items:
        errors.append("no_frozen_items")
    if len(items) > max(0, int(max_items)):
        errors.append("frozen_item_count_exceeds_max")

    indices: list[int] = []
    event_keys: set[str] = set()
    delta_keys: set[str] = set()
    for item in items:
        if str(item.get("run_key", "")).strip() != run_key:
            errors.append("dailyitem_wrong_run_key")
        if str(item.get("attempt_id", "")).strip() != attempt_id:
            errors.append("dailyitem_wrong_attempt_id")
        if str(item.get("schema_version", "")).strip() != "v11.0":
            errors.append("dailyitem_schema_version_not_v11")
        if not str(item.get("title", "")).strip():
            errors.append("dailyitem_missing_title")
        if not str(item.get("primary_url", "")).strip():
            errors.append("dailyitem_missing_primary_url")
        try:
            indices.append(int(float(str(item.get("item_index", "")))))
        except ValueError:
            errors.append("dailyitem_invalid_item_index")

        event_key = str(item.get("event_key_v11", "")).strip()
        delta_key = str(item.get("delta_key", "")).strip()
        if not event_key:
            errors.append("dailyitem_missing_event_key_v11")
        elif event_key in event_keys:
            errors.append("duplicate_dailyitem_event_key_v11")
        event_keys.add(event_key)
        if not delta_key:
            errors.append("dailyitem_missing_delta_key")
        elif delta_key in delta_keys:
            errors.append("duplicate_dailyitem_delta_key")
        delta_keys.add(delta_key)

        candidate = selected.get(delta_key)
        if candidate is None:
            errors.append("dailyitem_not_from_selected_candidate")
        elif str(candidate.get("event_key_v11", "")).strip() != event_key:
            errors.append("dailyitem_candidate_event_key_mismatch")

    if sorted(indices) != list(range(1, len(items) + 1)):
        errors.append("dailyitem_indices_not_contiguous")
    if len(selected) != len(items):
        errors.append("selected_candidate_count_mismatch")

    matching_runs = [
        row
        for row in runs
        if str(row.get("run_key", "")).strip() == run_key
        and str(row.get("attempt_id", "")).strip() == attempt_id
    ]
    if len(matching_runs) != 1:
        errors.append("shadow_attempt_row_count_not_one")
    else:
        run = matching_runs[0]
        if str(run.get("stage", "")).strip() != "freeze":
            errors.append("run_stage_not_freeze")
        if str(run.get("state_status", "")).strip() != "committed":
            errors.append("run_state_not_committed")
        if str(run.get("delivery_status", "")).strip() not in {"", "not_started"}:
            errors.append("shadow_delivery_started")
        if str(run.get("resume_stage", "")).strip() != "report":
            errors.append("resume_stage_not_report")
        if str(run.get("canonical_attempt", "")).strip():
            errors.append("shadow_attempt_must_not_be_canonical")
        if _int(run.get("frozen_item_count")) != len(items):
            errors.append("frozen_item_count_mismatch")
        if _int(run.get("selected_count")) != len(items):
            errors.append("selected_count_mismatch")
        if str(run.get("write_status", "")).strip() != "success":
            errors.append("write_status_not_success")
        if str(run.get("readback_status", "")).strip() != "success":
            errors.append("readback_status_not_success")
        if not _truthy(run.get("readback_match")):
            errors.append("readback_match_not_true")
        expected = frozen_manifest_fingerprint([dict(item) for item in items])
        if str(run.get("frozen_content_fingerprint", "")).strip() != expected:
            errors.append("frozen_fingerprint_mismatch")

    if any(
        str(row.get("last_reported_run", "")).strip() == run_key
        or str(row.get("run_key", "")).strip() == run_key
        for row in events
    ):
        errors.append("shadow_eventindex_write_forbidden")

    return sorted(set(errors))
