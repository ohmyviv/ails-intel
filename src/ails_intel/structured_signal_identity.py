from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, MutableMapping

from ails_intel.models import CoverageRecord


RouteIdentity = tuple[str, str, str, str]


def _text(value: object) -> str:
    return str(value or "").strip()


def make_structured_route_identity(
    producer_id: str,
    channel_id: str,
    route_id: str,
    source_id: str,
) -> RouteIdentity:
    return (
        _text(producer_id),
        _text(channel_id),
        _text(route_id),
        _text(source_id),
    )


def structured_signal_set_digest(signal_keys: Iterable[str]) -> str:
    """Return a deterministic, content-safe digest for a Signal identity set."""
    payload = "\n".join(sorted({_text(key) for key in signal_keys if _text(key)}))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def structured_active_signal_sets(
    *,
    run_key: str,
    active_signals: Iterable[Mapping[str, object]],
) -> tuple[dict[RouteIdentity, set[str]], list[str]]:
    """Materialize unique active structured Signal keys by persisted route identity.

    The returned sets describe ledger reality, not raw collector observations.
    Duplicate active rows with the same ``signal_key`` remain an integrity error
    even though a Python set would otherwise collapse them.
    """
    signal_sets: dict[RouteIdentity, set[str]] = {}
    errors: list[str] = []

    for row in active_signals:
        if _text(row.get("run_key")) != run_key:
            continue
        if _text(row.get("signal_state")) != "active":
            continue
        producer_id = _text(row.get("producer_id"))
        if not producer_id.startswith("collector/"):
            continue

        route = make_structured_route_identity(
            producer_id,
            _text(row.get("channel_id")),
            _text(row.get("route_id")),
            _text(row.get("source_id")),
        )
        if not all(route):
            errors.append("structured_signal_route_identity_incomplete")
            continue

        signal_key = _text(row.get("signal_key"))
        if not signal_key:
            errors.append("structured_signal_key_missing")
            continue

        keys = signal_sets.setdefault(route, set())
        if signal_key in keys:
            errors.append("structured_signal_key_duplicate")
        keys.add(signal_key)

    return signal_sets, sorted(set(errors))


def reconcile_expected_structured_signal_sets(
    *,
    expected_signal_sets: Mapping[RouteIdentity, set[str]],
    persisted_signal_sets: Mapping[RouteIdentity, set[str]],
) -> list[str]:
    """Fail closed when the expected and fresh-read structured Signal sets differ."""
    for route in set(expected_signal_sets) | set(persisted_signal_sets):
        expected = set(expected_signal_sets.get(route, set()))
        persisted = set(persisted_signal_sets.get(route, set()))
        if expected != persisted:
            return ["structured_signal_set_identity_mismatch"]
    return []


def assign_persisted_relevant_signal_counts(
    *,
    coverage_records: Iterable[CoverageRecord],
    persisted_signal_sets: Mapping[RouteIdentity, set[str]],
) -> list[str]:
    """Set Coverage ``relevant_signal_count`` from fresh-read unique Signals.

    ``hit_count`` intentionally remains the raw relevant-observation count from
    the collector. This function changes only the durable Signal-count semantic.
    """
    errors: list[str] = []
    seen_routes: set[RouteIdentity] = set()

    for record in coverage_records:
        row: MutableMapping[str, object] = record.values
        producer_id = _text(row.get("producer_id"))
        if not producer_id.startswith("collector/"):
            continue
        route = make_structured_route_identity(
            producer_id,
            _text(row.get("channel_id")),
            _text(row.get("route_id")),
            _text(row.get("source_id")),
        )
        if not all(route):
            errors.append("structured_coverage_route_identity_incomplete")
            continue
        if route in seen_routes:
            errors.append("structured_coverage_route_identity_duplicate")
            continue
        seen_routes.add(route)
        row["relevant_signal_count"] = len(persisted_signal_sets.get(route, set()))

    return sorted(set(errors))


def validate_structured_coverage_signal_identity(
    *,
    run_key: str,
    coverage_rows: Iterable[Mapping[str, object]],
    active_signals: Iterable[Mapping[str, object]],
) -> list[str]:
    """Reconcile persisted Coverage counts against active structured Signal keys.

    This is intentionally per-route. Equal global totals cannot hide a missing
    Signal on one route and an unexpected Signal on another.
    """
    signal_sets, errors = structured_active_signal_sets(
        run_key=run_key,
        active_signals=active_signals,
    )
    seen_routes: set[RouteIdentity] = set()

    for row in coverage_rows:
        if _text(row.get("run_key")) != run_key:
            continue
        producer_id = _text(row.get("producer_id"))
        if not producer_id.startswith("collector/"):
            continue
        route = make_structured_route_identity(
            producer_id,
            _text(row.get("channel_id")),
            _text(row.get("route_id")),
            _text(row.get("source_id")),
        )
        if not all(route):
            errors.append("structured_coverage_route_identity_incomplete")
            continue
        if route in seen_routes:
            errors.append("structured_coverage_route_identity_duplicate")
            continue
        seen_routes.add(route)

        try:
            declared = int(float(_text(row.get("relevant_signal_count")) or "0"))
        except ValueError:
            errors.append("structured_coverage_relevant_signal_count_invalid")
            continue
        if declared < 0:
            errors.append("structured_coverage_relevant_signal_count_invalid")
            continue
        if declared != len(signal_sets.get(route, set())):
            errors.append("structured_signal_set_identity_mismatch")

    return sorted(set(errors))
