from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

CHALLENGER_HEADERS = [
    "challenger_id",
    "report_date",
    "run_key",
    "audit_attempt_id",
    "provider_id",
    "received_at_bjt",
    "raw_title",
    "raw_url",
    "raw_summary",
    "claimed_source_published_at",
    "claimed_event_date",
    "entity_hint",
    "event_type_hint",
    "content_class_hint",
    "matched_signal_ids",
    "matched_candidate_ids",
    "matched_event_key",
    "disposition",
    "miss_type",
    "miss_severity",
    "primary_source_status",
    "canonical_primary_url",
    "source_published_at",
    "first_public_at",
    "event_date",
    "audited_at_bjt",
    "notes",
    "schema_version",
]

CHALLENGER_DISPOSITIONS = {
    "confirmed_miss",
    "stale_resurfacing",
    "duplicate_known_event",
    "scope_mismatch",
    "evidence_insufficient",
    "false_or_inaccurate_claim",
}
MISS_TYPES = {"discovery_miss", "verification_miss", "selection_miss", "timing_miss"}
MISS_SEVERITIES = {"critical", "material", "minor"}
PRIMARY_SOURCE_STATUSES = {"verified", "unverified", "not_found", "not_required"}


@dataclass(frozen=True)
class ChallengerMissSummary:
    confirmed_misses: int
    critical_misses: int
    material_misses: int


def _canonical_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc:
        return text
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def _normalized_title(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def make_challenger_id(report_date: str, provider_id: str, raw_url: str, raw_title: str) -> str:
    payload = "|".join(
        [
            str(report_date).strip(),
            str(provider_id).strip().casefold(),
            _canonical_url(raw_url),
            _normalized_title(raw_title),
        ]
    )
    return "CHL-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _as_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _int_value(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return None


def validate_challenger_row(
    row: Mapping[str, object],
    *,
    report_date: str | None = None,
    run_key: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
) -> list[str]:
    errors: list[str] = []

    row_report_date = str(row.get("report_date", "")).strip()
    row_run_key = str(row.get("run_key", "")).strip()
    provider_id = str(row.get("provider_id", "")).strip()
    raw_title = str(row.get("raw_title", "")).strip()
    raw_url = str(row.get("raw_url", "")).strip()
    challenger_id = str(row.get("challenger_id", "")).strip()
    disposition = str(row.get("disposition", "")).strip()
    primary_status = str(row.get("primary_source_status", "")).strip()

    for field, value in (
        ("report_date", row_report_date),
        ("run_key", row_run_key),
        ("audit_attempt_id", str(row.get("audit_attempt_id", "")).strip()),
        ("provider_id", provider_id),
        ("received_at_bjt", str(row.get("received_at_bjt", "")).strip()),
        ("raw_title", raw_title),
        ("raw_url", raw_url),
        ("audited_at_bjt", str(row.get("audited_at_bjt", "")).strip()),
    ):
        if not value:
            errors.append(f"challenger_missing_{field}")

    if row_report_date and _as_date(row_report_date) is None:
        errors.append("challenger_invalid_report_date")
    if report_date and row_report_date != report_date:
        errors.append("challenger_report_date_mismatch")
    if run_key and row_run_key != run_key:
        errors.append("challenger_run_key_mismatch")

    if challenger_id:
        expected_id = make_challenger_id(row_report_date, provider_id, raw_url, raw_title)
        if challenger_id != expected_id:
            errors.append("challenger_id_mismatch")
    else:
        errors.append("challenger_missing_challenger_id")

    if disposition not in CHALLENGER_DISPOSITIONS:
        errors.append("challenger_invalid_disposition")
    if primary_status not in PRIMARY_SOURCE_STATUSES:
        errors.append("challenger_invalid_primary_source_status")

    if str(row.get("schema_version", "")).strip() != "v11.2":
        errors.append("challenger_schema_version_not_v11_2")

    received = _as_datetime(row.get("received_at_bjt"))
    audited = _as_datetime(row.get("audited_at_bjt"))
    if str(row.get("received_at_bjt", "")).strip() and received is None:
        errors.append("challenger_invalid_received_at")
    if str(row.get("audited_at_bjt", "")).strip() and audited is None:
        errors.append("challenger_invalid_audited_at")
    if received and audited and audited < received:
        errors.append("challenger_audited_before_received")

    source_published = _as_date(row.get("source_published_at"))
    first_public = _as_date(row.get("first_public_at"))
    event_date = _as_date(row.get("event_date"))

    if disposition == "confirmed_miss":
        miss_type = str(row.get("miss_type", "")).strip()
        severity = str(row.get("miss_severity", "")).strip()
        if miss_type not in MISS_TYPES:
            errors.append("confirmed_miss_missing_or_invalid_type")
        if severity not in MISS_SEVERITIES:
            errors.append("confirmed_miss_missing_or_invalid_severity")
        if primary_status != "verified":
            errors.append("confirmed_miss_primary_not_verified")
        if not str(row.get("canonical_primary_url", "")).strip():
            errors.append("confirmed_miss_missing_primary_url")
        if first_public is None and event_date is None:
            errors.append("confirmed_miss_missing_time_provenance")

        anchor = first_public or event_date
        start = _as_date(window_start) if window_start else None
        end = _as_date(window_end) if window_end else None
        if window_start and start is None:
            errors.append("challenger_invalid_window_start")
        if window_end and end is None:
            errors.append("challenger_invalid_window_end")
        if anchor and start and anchor < start:
            errors.append("confirmed_miss_outside_window")
        if anchor and end and anchor > end:
            errors.append("confirmed_miss_outside_window")
    else:
        if str(row.get("miss_type", "")).strip():
            errors.append("nonmiss_has_miss_type")
        if str(row.get("miss_severity", "")).strip():
            errors.append("nonmiss_has_miss_severity")

    if disposition == "duplicate_known_event" and not str(row.get("matched_event_key", "")).strip():
        errors.append("duplicate_known_event_missing_event_key")

    if disposition == "stale_resurfacing":
        claimed_source = _as_date(row.get("claimed_source_published_at")) or source_published
        underlying = first_public or event_date
        if underlying is None:
            errors.append("stale_resurfacing_missing_underlying_date")
        elif claimed_source is None:
            errors.append("stale_resurfacing_missing_source_date")
        elif underlying >= claimed_source and not str(row.get("matched_event_key", "")).strip():
            errors.append("stale_resurfacing_not_proven_stale")

    if disposition == "evidence_insufficient" and primary_status == "verified":
        errors.append("evidence_insufficient_marked_verified")

    return sorted(set(errors))


def summarize_confirmed_misses(rows: Iterable[Mapping[str, object]]) -> ChallengerMissSummary:
    confirmed = 0
    critical = 0
    material = 0
    for row in rows:
        if str(row.get("disposition", "")).strip() != "confirmed_miss":
            continue
        confirmed += 1
        severity = str(row.get("miss_severity", "")).strip()
        if severity == "critical":
            critical += 1
        elif severity == "material":
            material += 1
    return ChallengerMissSummary(confirmed, critical, material)


def validate_challenger_audit_snapshot(
    *,
    rows: Iterable[Mapping[str, object]],
    report_date: str,
    run_key: str,
    window_start: str | None = None,
    window_end: str | None = None,
    run_row: Mapping[str, object] | None = None,
) -> list[str]:
    errors: list[str] = []
    materialized = list(rows)
    ids: set[str] = set()

    for row in materialized:
        errors.extend(
            validate_challenger_row(
                row,
                report_date=report_date,
                run_key=run_key,
                window_start=window_start,
                window_end=window_end,
            )
        )
        challenger_id = str(row.get("challenger_id", "")).strip()
        if challenger_id:
            if challenger_id in ids:
                errors.append("duplicate_challenger_id")
            ids.add(challenger_id)

    if run_row is not None:
        summary = summarize_confirmed_misses(materialized)
        declared = {
            "confirmed_misses": summary.confirmed_misses,
            "critical_misses": summary.critical_misses,
            "material_misses": summary.material_misses,
        }
        for field, expected in declared.items():
            actual = _int_value(run_row.get(field))
            if actual is None:
                errors.append(f"challenger_invalid_run_{field}")
            elif actual != expected:
                errors.append(f"challenger_run_{field}_mismatch")

    return sorted(set(errors))
