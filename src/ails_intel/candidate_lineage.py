from __future__ import annotations

from collections.abc import Iterable, Mapping

from ails_intel.worker_contract import parse_signal_ids


def _text(value: object) -> str:
    return str(value or "").strip()


def _note_fields(notes: object) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in _text(notes).split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            fields[key] = value.strip()
    return fields


def _ctgov_expected_lineage(signal: Mapping[str, object]) -> tuple[str, str, str] | None:
    """Return the authoritative CT.gov Candidate lineage encoded by a Signal.

    Structured ClinicalTrials.gov Signals persist the material-delta class in
    ``notes``.  ``stable_id`` identifies the study, the update/event date
    identifies the delta occurrence, and ``first_public_at_hint`` preserves the
    original registration date.  Candidate formation must not silently recast a
    later material update as a fresh registration.
    """
    meta = _note_fields(signal.get("notes"))
    delta = _text(meta.get("ctgov_delta"))
    if not delta:
        return None

    stable_id = _text(signal.get("stable_id"))
    event_date = _text(signal.get("event_date_hint")) or _text(signal.get("published_at_hint"))
    first_public_at = _text(signal.get("first_public_at_hint"))
    if not stable_id or not event_date:
        return ("", "", first_public_at)
    return (f"{stable_id}|{delta}|{event_date}", delta, first_public_at)


def validate_candidate_signal_lineage(
    *,
    candidates: Iterable[Mapping[str, object]],
    active_signals: Iterable[Mapping[str, object]],
) -> list[str]:
    """Fail closed when a Candidate rewrites authoritative Signal lineage.

    The first enforced source-specific invariant is ClinicalTrials.gov because
    its Structured Collector already records a material-delta class.  The
    validator is intentionally independent of run namespace so it can be used
    both before Candidate persistence and again during final reconciliation.
    """
    signals_by_id = {
        _text(row.get("signal_id")): row
        for row in active_signals
        if _text(row.get("signal_id")) and _text(row.get("signal_state")) == "active"
    }
    errors: list[str] = []

    for candidate in candidates:
        expected: set[tuple[str, str, str]] = set()
        for signal_id in parse_signal_ids(candidate.get("source_signal_ids")):
            signal = signals_by_id.get(signal_id)
            if signal is None:
                continue
            lineage = _ctgov_expected_lineage(signal)
            if lineage is not None:
                expected.add(lineage)

        if not expected:
            continue
        if any(not key for key, _delta, _first_public in expected):
            errors.append("candidate_ctgov_lineage_incomplete")
            continue
        if len(expected) != 1:
            errors.append("candidate_ctgov_lineage_ambiguous")
            continue

        expected_key, _delta, expected_first_public = next(iter(expected))
        if _text(candidate.get("delta_key")) != expected_key:
            errors.append("candidate_ctgov_delta_key_mismatch")
        if _text(candidate.get("event_key_v11")) != expected_key:
            errors.append("candidate_ctgov_event_key_mismatch")
        if expected_first_public and _text(candidate.get("first_public_at")) != expected_first_public:
            errors.append("candidate_ctgov_first_public_at_mismatch")

    return sorted(set(errors))
