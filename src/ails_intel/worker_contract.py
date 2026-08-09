from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping

SHADOW_RUN_RE = re.compile(r"^AILS11S-(\d{8})-\d{4}-BJT$")
ATTEMPT_RE = re.compile(r"-A(\d+)$")
CANDIDATE_DISPOSITIONS = {"selected", "rejected", "pending", "expired", "superseded"}
PRIORITIES = {"P0", "P1", "P2"}
PENDING_TYPES = {
    "awaiting_financing_close",
    "awaiting_primary_confirmation",
    "awaiting_clinical_data",
    "awaiting_regulatory_decision",
    "awaiting_deal_terms",
    "awaiting_publication",
    "other",
}


def next_attempt_id(run_key: str, existing_attempt_ids: Iterable[str]) -> str:
    """Return the next append-only shadow attempt ID for a run.

    Existing rows may contain either full IDs (``<run_key>-A1``) or legacy short
    attempt labels (``A1``). The returned form is always fully qualified so a
    public validator never needs private state to disambiguate it.
    """
    seen: set[int] = set()
    for raw in existing_attempt_ids:
        value = str(raw).strip()
        if not value:
            continue
        if value.startswith("A") and value[1:].isdigit():
            seen.add(int(value[1:]))
            continue
        match = ATTEMPT_RE.search(value)
        if match:
            seen.add(int(match.group(1)))
    n = 1
    while n in seen:
        n += 1
    return f"{run_key}-A{n}"


def make_candidate_id(run_key: str, attempt_id: str, delta_key: str) -> str:
    match = SHADOW_RUN_RE.match(run_key)
    date_token = match.group(1) if match else "00000000"
    material = f"{run_key}|{attempt_id}|{delta_key}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:12]
    return f"CAN-{date_token}-{digest}"


def parse_signal_ids(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    # The Sheet contract stores compact IDs in a single cell. Accept the two
    # separators used by human/worker writers while keeping the parser simple.
    return [x.strip() for x in re.split(r"[|,]", text) if x.strip()]


def validate_candidate(candidate: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    required = {
        "candidate_id",
        "run_key",
        "attempt_id",
        "source_signal_ids",
        "event_key_v11",
        "delta_key",
        "priority_class",
        "disposition",
        "schema_version",
    }
    for key in sorted(required):
        if not str(candidate.get(key, "")).strip():
            errors.append(f"candidate_missing:{key}")

    disposition = str(candidate.get("disposition", "")).strip()
    priority = str(candidate.get("priority_class", "")).strip()
    if disposition and disposition not in CANDIDATE_DISPOSITIONS:
        errors.append("candidate_invalid:disposition")
    if priority and priority not in PRIORITIES:
        errors.append("candidate_invalid:priority_class")
    if str(candidate.get("schema_version", "")).strip() not in {"", "v11.0"}:
        errors.append("candidate_invalid:schema_version")

    if disposition == "pending":
        if priority not in {"P0", "P1"}:
            errors.append("pending_requires_p0_or_p1")
        for key in ("pending_type", "missing_evidence", "retry_after", "expiry_date"):
            if not str(candidate.get(key, "")).strip():
                errors.append(f"pending_missing:{key}")
        pending_type = str(candidate.get("pending_type", "")).strip()
        if pending_type and pending_type not in PENDING_TYPES:
            errors.append("pending_invalid:pending_type")

    if not parse_signal_ids(candidate.get("source_signal_ids")):
        errors.append("candidate_missing:source_signal_ids")
    return errors


def collector_diagnostics(coverage_rows: Iterable[Mapping[str, object]]) -> dict[str, int]:
    failures = 0
    saturations = 0
    for row in coverage_rows:
        if str(row.get("execution_status", "")).strip() == "failed":
            failures += 1
        if str(row.get("saturation_status", "")).strip() == "saturated":
            saturations += 1
    return {
        "collector_failure_count": failures,
        "collector_saturation_count": saturations,
    }


def validate_shadow_worker_snapshot(
    *,
    run_key: str,
    attempt_id: str,
    active_signals: Iterable[Mapping[str, object]],
    candidates: Iterable[Mapping[str, object]],
    run_rows: Iterable[Mapping[str, object]],
    daily_items: Iterable[Mapping[str, object]],
    event_index_rows: Iterable[Mapping[str, object]],
) -> list[str]:
    """Validate the Sprint-3A ownership and referential-integrity boundary.

    Sprint 3A may write only one shadow run attempt and verified Candidate rows.
    DailyItems and EventIndex are deliberately out of scope until later sprints.
    """
    errors: list[str] = []
    if not SHADOW_RUN_RE.match(run_key):
        errors.append("run_key_not_shadow")
    if not attempt_id.startswith(f"{run_key}-A"):
        errors.append("attempt_id_not_qualified")

    signal_rows = list(active_signals)
    candidate_rows = list(candidates)
    runs = list(run_rows)
    daily = list(daily_items)
    events = list(event_index_rows)

    active_by_id = {
        str(row.get("signal_id", "")).strip(): row
        for row in signal_rows
        if str(row.get("signal_state", "")).strip() == "active"
        and str(row.get("signal_id", "")).strip()
    }
    if not active_by_id:
        errors.append("no_active_signals")

    candidate_ids: set[str] = set()
    delta_keys: set[str] = set()
    for candidate in candidate_rows:
        if str(candidate.get("run_key", "")).strip() != run_key:
            errors.append("candidate_wrong_run_key")
        if str(candidate.get("attempt_id", "")).strip() != attempt_id:
            errors.append("candidate_wrong_attempt_id")
        errors.extend(validate_candidate(candidate))

        cid = str(candidate.get("candidate_id", "")).strip()
        if cid in candidate_ids:
            errors.append("duplicate_candidate_id")
        candidate_ids.add(cid)

        delta_key = str(candidate.get("delta_key", "")).strip()
        if delta_key in delta_keys:
            errors.append("duplicate_delta_key")
        delta_keys.add(delta_key)

        for signal_id in parse_signal_ids(candidate.get("source_signal_ids")):
            if signal_id not in active_by_id:
                errors.append("candidate_references_nonactive_signal")

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
        if str(run.get("state_status", "")).strip() != "verified":
            errors.append("shadow_attempt_not_verified")
        if str(run.get("delivery_status", "")).strip() not in {"", "not_started"}:
            errors.append("shadow_attempt_delivery_started")
        if str(run.get("canonical_attempt", "")).strip():
            errors.append("shadow_attempt_must_not_be_canonical")
        try:
            declared = int(float(str(run.get("candidate_count", "0") or "0")))
        except ValueError:
            declared = -1
        if declared != len(candidate_rows):
            errors.append("candidate_count_mismatch")
        if str(run.get("schema_version", "")).strip() != "v11.0":
            errors.append("run_schema_version_not_v11")

    if any(str(row.get("run_key", "")).strip() == run_key for row in daily):
        errors.append("sprint3a_dailyitems_write_forbidden")
    if any(
        str(row.get("last_reported_run", "")).strip() == run_key
        or str(row.get("run_key", "")).strip() == run_key
        for row in events
    ):
        errors.append("sprint3a_eventindex_write_forbidden")

    # De-duplicate repeated error labels so the validator remains compact and
    # does not leak row-level private content into public Actions logs.
    return sorted(set(errors))
