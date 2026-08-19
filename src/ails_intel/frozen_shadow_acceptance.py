from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ails_intel.unified_ingestion import structured_snapshot_fingerprint
from ails_intel.worker_contract import SHADOW_RUN_RE


def _text(value: object) -> str:
    return str(value or "").strip()


def _date_token(run_key: str) -> str:
    parts = _text(run_key).split("-")
    return parts[1] if len(parts) > 1 and len(parts[1]) == 8 else ""


@dataclass(frozen=True)
class FrozenShadowAcceptanceProjection:
    active_signals: tuple[dict[str, object], ...]
    coverage_rows: tuple[dict[str, object], ...]
    source_signal_count: int
    source_coverage_count: int
    qualified_fingerprint: str
    errors: tuple[str, ...]


def project_frozen_structured_for_shadow_acceptance(
    *,
    run_key: str,
    source_run_key: str,
    source_attempt_id: str,
    qualified_source_signals: Iterable[Mapping[str, object]],
    qualified_source_coverage: Iterable[Mapping[str, object]],
    expected_qualified_fingerprint: str,
    current_active_signals: Iterable[Mapping[str, object]],
    current_coverage_rows: Iterable[Mapping[str, object]],
) -> FrozenShadowAcceptanceProjection:
    """Create a read-only current-run view of an authorized Frozen Structured source.

    This helper exists for downstream-only manual Shadow acceptance. It never
    writes or rewrites the source snapshot. Instead it verifies the explicitly
    qualified source fingerprint, then projects collector rows into the manual
    run namespace *in memory* so the unchanged final ledger acceptance contract
    can evaluate one coherent Signal/Coverage snapshot.

    Current-run Worker/Rescue evidence is preserved as persisted. Current-run
    collector rows are rejected to prevent accidental mixing of a rerun
    Structured snapshot with the declared frozen source.
    """
    manual_run = _text(run_key)
    source_run = _text(source_run_key)
    source_attempt = _text(source_attempt_id)
    expected = _text(expected_qualified_fingerprint)
    errors: list[str] = []

    if not SHADOW_RUN_RE.match(manual_run) or not manual_run.startswith("AILS11M-"):
        errors.append("frozen_acceptance_requires_manual_shadow")
    if not SHADOW_RUN_RE.match(source_run) or not source_run.startswith("AILS11S-"):
        errors.append("frozen_acceptance_source_not_scheduled_shadow")
    if not source_attempt.startswith(f"{source_run}-A"):
        errors.append("frozen_acceptance_source_attempt_invalid")
    if not _date_token(manual_run) or _date_token(manual_run) != _date_token(source_run):
        errors.append("frozen_acceptance_report_date_mismatch")
    if not expected:
        errors.append("frozen_acceptance_qualified_fingerprint_missing")

    source_signals = [
        dict(row)
        for row in qualified_source_signals
        if _text(row.get("run_key")) == source_run
        and _text(row.get("origin_attempt_id")) == source_attempt
        and _text(row.get("producer_id")).startswith("collector/")
        and _text(row.get("signal_state")) == "active"
    ]
    source_coverage = [
        dict(row)
        for row in qualified_source_coverage
        if _text(row.get("run_key")) == source_run
        and _text(row.get("attempt_id")) == source_attempt
        and _text(row.get("producer_id")).startswith("collector/")
    ]
    if not source_signals:
        errors.append("frozen_acceptance_source_signals_missing")
    if not source_coverage:
        errors.append("frozen_acceptance_source_coverage_missing")

    actual = structured_snapshot_fingerprint(
        run_key=source_run,
        attempt_id=source_attempt,
        active_signals=source_signals,
        coverage_rows=source_coverage,
    )
    if expected and actual != expected:
        errors.append("frozen_acceptance_qualified_fingerprint_mismatch")

    current_signals = [dict(row) for row in current_active_signals]
    current_coverage = [dict(row) for row in current_coverage_rows]
    if any(
        _text(row.get("run_key")) == manual_run
        and _text(row.get("producer_id")).startswith("collector/")
        for row in current_signals
    ):
        errors.append("frozen_acceptance_manual_structured_signals_present")
    if any(
        _text(row.get("run_key")) == manual_run
        and _text(row.get("producer_id")).startswith("collector/")
        for row in current_coverage
    ):
        errors.append("frozen_acceptance_manual_structured_coverage_present")

    if errors:
        return FrozenShadowAcceptanceProjection(
            active_signals=tuple(current_signals),
            coverage_rows=tuple(current_coverage),
            source_signal_count=len(source_signals),
            source_coverage_count=len(source_coverage),
            qualified_fingerprint=actual,
            errors=tuple(sorted(set(errors))),
        )

    combined_signals: list[dict[str, object]] = []
    current_ids: set[str] = set()
    for row in current_signals:
        if _text(row.get("run_key")) != manual_run:
            continue
        signal_id = _text(row.get("signal_id"))
        if signal_id:
            current_ids.add(signal_id)
        combined_signals.append(row)

    for row in source_signals:
        projected = dict(row)
        projected["run_key"] = manual_run
        signal_id = _text(projected.get("signal_id"))
        # Stable same-day Signal IDs can legitimately be independently
        # rediscovered. Preserve the current-run row rather than duplicate it.
        if signal_id and signal_id in current_ids:
            continue
        combined_signals.append(projected)
        if signal_id:
            current_ids.add(signal_id)

    combined_coverage = [
        row for row in current_coverage if _text(row.get("run_key")) == manual_run
    ]
    for row in source_coverage:
        projected = dict(row)
        projected["run_key"] = manual_run
        combined_coverage.append(projected)

    return FrozenShadowAcceptanceProjection(
        active_signals=tuple(combined_signals),
        coverage_rows=tuple(combined_coverage),
        source_signal_count=len(source_signals),
        source_coverage_count=len(source_coverage),
        qualified_fingerprint=actual,
        errors=(),
    )
