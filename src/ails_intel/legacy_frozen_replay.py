from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ails_intel.models import COVERAGE_HEADERS, SIGNAL_HEADERS
from ails_intel.unified_ingestion import structured_snapshot_fingerprint
from ails_intel.worker_contract import SHADOW_RUN_RE


@dataclass(frozen=True)
class QualifiedLegacyStructuredSnapshot:
    """In-memory attempt-qualified view of one immutable legacy snapshot."""

    active_signals: tuple[dict[str, object], ...]
    coverage_rows: tuple[dict[str, object], ...]
    persisted_fingerprint: str
    qualified_fingerprint: str


def _text(value: object) -> str:
    return str(value or "").strip()


def _structured_route_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        _text(row.get("producer_id")),
        _text(row.get("channel_id")),
        _text(row.get("route_id")),
        _text(row.get("source_id")),
    )


def legacy_structured_snapshot_fingerprint(
    *,
    run_key: str,
    active_signals: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
) -> str:
    """Fingerprint the persisted, pre-attempt-provenance Structured snapshot.

    This fingerprint deliberately hashes the historical rows as they actually
    exist. It never injects or rewrites attempt provenance.
    """
    signal_lines: list[str] = []
    for row in active_signals:
        if _text(row.get("run_key")) != run_key:
            continue
        if _text(row.get("signal_state")) != "active":
            continue
        if not _text(row.get("producer_id")).startswith("collector/"):
            continue
        signal_lines.append(
            "S|" + "\x1f".join(_text(row.get(header)) for header in SIGNAL_HEADERS)
        )

    coverage_lines: list[str] = []
    for row in coverage_rows:
        if _text(row.get("run_key")) != run_key:
            continue
        if not _text(row.get("producer_id")).startswith("collector/"):
            continue
        coverage_lines.append(
            "C|" + "\x1f".join(_text(row.get(header)) for header in COVERAGE_HEADERS)
        )

    payload = "\n".join(sorted(signal_lines) + sorted(coverage_lines)).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def qualify_legacy_frozen_structured_snapshot(
    *,
    source_run_key: str,
    source_attempt_id: str,
    source_attempt_ids: Iterable[str],
    active_signals: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
    expected_persisted_fingerprint: str,
) -> QualifiedLegacyStructuredSnapshot:
    """Authorize a narrow pre-contract snapshot without editing history.

    The adapter is intentionally separate from the normal unified-ingestion
    validator. It accepts only a scheduled Shadow source whose durable Run
    ledger proves exactly one attempt; all source collector rows must have blank
    attempt provenance; Structured Signal/Coverage identities must reconcile at
    route level; and the caller-supplied fingerprint must match the full
    persisted legacy snapshot. On success it returns copies with attempt fields
    populated *in memory* so the unchanged strict frozen-input validator can be
    used downstream.
    """
    source_run = _text(source_run_key)
    source_attempt = _text(source_attempt_id)
    expected = _text(expected_persisted_fingerprint)
    errors: list[str] = []

    if not SHADOW_RUN_RE.match(source_run) or not source_run.startswith("AILS11S-"):
        errors.append("legacy_frozen_source_not_scheduled_shadow")
    if not source_attempt.startswith(f"{source_run}-A"):
        errors.append("legacy_frozen_attempt_not_qualified")
    durable_attempts = sorted({_text(value) for value in source_attempt_ids if _text(value)})
    if durable_attempts != [source_attempt]:
        errors.append("legacy_frozen_source_attempt_not_unique")
    if not expected:
        errors.append("legacy_frozen_persisted_fingerprint_missing")

    source_signals = [
        row
        for row in active_signals
        if _text(row.get("run_key")) == source_run
        and _text(row.get("signal_state")) == "active"
        and _text(row.get("producer_id")).startswith("collector/")
    ]
    source_coverage = [
        row
        for row in coverage_rows
        if _text(row.get("run_key")) == source_run
        and _text(row.get("producer_id")).startswith("collector/")
    ]

    if not source_signals:
        errors.append("legacy_frozen_has_no_active_structured_signals")
    if not source_coverage:
        errors.append("legacy_frozen_has_no_structured_coverage")
    if any(_text(row.get("origin_attempt_id")) for row in source_signals):
        errors.append("legacy_frozen_signal_provenance_not_uniformly_blank")
    if any(_text(row.get("attempt_id")) for row in source_coverage):
        errors.append("legacy_frozen_coverage_provenance_not_uniformly_blank")

    signal_ids: set[str] = set()
    signal_keys: set[str] = set()
    signal_route_counts: dict[tuple[str, str, str, str], int] = {}
    for row in source_signals:
        signal_id = _text(row.get("signal_id"))
        signal_key = _text(row.get("signal_key"))
        route_key = _structured_route_key(row)
        if not signal_id:
            errors.append("legacy_frozen_signal_id_missing")
        elif signal_id in signal_ids:
            errors.append("legacy_frozen_duplicate_signal_id")
        else:
            signal_ids.add(signal_id)
        if not signal_key:
            errors.append("legacy_frozen_signal_key_missing")
        elif signal_key in signal_keys:
            errors.append("legacy_frozen_duplicate_signal_key")
        else:
            signal_keys.add(signal_key)
        if not all(route_key):
            errors.append("legacy_frozen_signal_route_identity_missing")
            continue
        signal_route_counts[route_key] = signal_route_counts.get(route_key, 0) + 1

    coverage_route_counts: dict[tuple[str, str, str, str], int] = {}
    seen_coverage_routes: set[tuple[str, str, str, str]] = set()
    for row in source_coverage:
        route_key = _structured_route_key(row)
        if not all(route_key):
            errors.append("legacy_frozen_coverage_route_identity_missing")
            continue
        if route_key in seen_coverage_routes:
            errors.append("legacy_frozen_duplicate_coverage_route")
        seen_coverage_routes.add(route_key)
        try:
            count = int(float(_text(row.get("relevant_signal_count")) or "0"))
        except ValueError:
            errors.append("legacy_frozen_coverage_count_invalid")
            continue
        if count < 0:
            errors.append("legacy_frozen_coverage_count_invalid")
            continue
        coverage_route_counts[route_key] = count

    if signal_route_counts != coverage_route_counts:
        errors.append("legacy_frozen_route_signal_count_mismatch")

    actual_persisted = legacy_structured_snapshot_fingerprint(
        run_key=source_run,
        active_signals=source_signals,
        coverage_rows=source_coverage,
    )
    if expected and actual_persisted != expected:
        errors.append("legacy_frozen_persisted_fingerprint_mismatch")

    if errors:
        raise ValueError(";".join(sorted(set(errors))))

    qualified_signals: list[dict[str, object]] = []
    for row in source_signals:
        qualified = dict(row)
        qualified["origin_attempt_id"] = source_attempt
        qualified_signals.append(qualified)

    qualified_coverage: list[dict[str, object]] = []
    for row in source_coverage:
        qualified = dict(row)
        qualified["attempt_id"] = source_attempt
        qualified_coverage.append(qualified)

    qualified_fingerprint = structured_snapshot_fingerprint(
        run_key=source_run,
        attempt_id=source_attempt,
        active_signals=qualified_signals,
        coverage_rows=qualified_coverage,
    )
    return QualifiedLegacyStructuredSnapshot(
        active_signals=tuple(qualified_signals),
        coverage_rows=tuple(qualified_coverage),
        persisted_fingerprint=actual_persisted,
        qualified_fingerprint=qualified_fingerprint,
    )
