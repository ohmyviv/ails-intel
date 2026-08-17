from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

from ails_intel.models import COVERAGE_HEADERS, SIGNAL_HEADERS, CoverageRecord, SignalRecord
from ails_intel.signal_keys import make_coverage_id, make_signal_id, make_signal_key
from ails_intel.snapshot_policy import enabled_structured_collector_ids
from ails_intel.worker_contract import SHADOW_RUN_RE, parse_signal_ids

WORKER_PRODUCERS = {"chatgpt/worker", "chatgpt/rescue"}
VALID_CHANNELS = {"C1", "C2", "C3", "C4", "C5", "C6"}
VALID_PRIORITIES = {"P0", "P1", "P2"}
VALID_CORE_HINTS = {"TRUE", "FALSE", "UNKNOWN"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _date_token(run_key: str) -> str:
    parts = str(run_key).split("-")
    return parts[1] if len(parts) > 1 and len(parts[1]) == 8 else "00000000"


def default_worker_priority(channel_id: str) -> str:
    return "P2" if channel_id == "C5" else "P1"


def build_worker_signal(
    *,
    run_key: str,
    attempt_id: str,
    batch_id: str,
    producer_id: str,
    discovered_at_bjt: str,
    channel_id: str,
    route_id: str,
    source_id: str,
    discovery_method: str,
    title: str,
    snippet: str,
    url: str,
    stable_id: str = "",
    published_at: str = "",
    first_public_at: str = "",
    event_date: str = "",
    entity_hint: str = "",
    action_hint: str = "",
    asset_hint: str = "",
    event_key_hint: str = "",
    priority_hint: str = "",
    ai_core_hint: str = "TRUE",
    life_science_core_hint: str = "TRUE",
    notes: str = "",
) -> SignalRecord:
    if producer_id not in WORKER_PRODUCERS:
        raise ValueError("worker signal producer must be chatgpt/worker or chatgpt/rescue")
    if channel_id not in VALID_CHANNELS:
        raise ValueError("invalid worker signal channel")
    if not str(route_id).strip():
        raise ValueError("worker signal requires route_id")
    if not str(title).strip() or not str(url).strip():
        raise ValueError("worker signal requires title and url")
    priority = str(priority_hint or default_worker_priority(channel_id)).strip()
    if priority not in VALID_PRIORITIES:
        raise ValueError("invalid worker signal priority")
    ai_core = str(ai_core_hint or "").strip().upper()
    life_science_core = str(life_science_core_hint or "").strip().upper()
    if ai_core not in VALID_CORE_HINTS or life_science_core not in VALID_CORE_HINTS:
        raise ValueError("invalid worker signal core hint")

    key_source = str(source_id).strip() or "unregistered_web"
    published_for_key = str(published_at or first_public_at or event_date).strip()
    key = make_signal_key(key_source, stable_id, url, title, published_for_key)
    return SignalRecord(
        {
            "signal_id": make_signal_id(_date_token(run_key), key),
            "run_key": run_key,
            "collection_batch_id": batch_id,
            "producer_id": producer_id,
            "origin_attempt_id": attempt_id,
            "discovered_at_bjt": discovered_at_bjt,
            "channel_id": channel_id,
            "route_id": route_id,
            "source_id": source_id,
            "discovery_method": discovery_method,
            "raw_title": title,
            "raw_snippet": snippet,
            "entity_hint": entity_hint,
            "action_hint": action_hint,
            "asset_hint": asset_hint,
            "event_date_hint": event_date,
            "published_at_hint": published_at,
            "first_public_at_hint": first_public_at,
            "url": url,
            "stable_id": stable_id,
            "signal_key": key,
            "event_key_hint": event_key_hint,
            "priority_hint": priority,
            "ai_core_hint": ai_core,
            "life_science_core_hint": life_science_core,
            "signal_state": "active",
            "notes": notes,
            "schema_version": "v11.0",
        }
    )


def build_worker_coverage(
    *,
    run_key: str,
    attempt_id: str,
    producer_id: str,
    channel_id: str,
    route_id: str,
    source_id: str = "",
    source_name: str = "",
    execution_status: str,
    checked_at_bjt: str,
    relevant_signal_count: int = 0,
    results_seen: int | str = "",
    representative_url: str = "",
    failure_reason: str = "",
    fallback_used: bool = False,
    saturation_status: str = "clear",
    source_group: str = "worker_discovery",
    route: str = "bounded web route",
    notes: str = "",
) -> CoverageRecord:
    if producer_id not in WORKER_PRODUCERS:
        raise ValueError("worker coverage producer must be chatgpt/worker or chatgpt/rescue")
    if channel_id not in VALID_CHANNELS or not route_id:
        raise ValueError("worker coverage requires valid channel and route")
    if execution_status not in {"complete", "partial", "failed", "skipped"}:
        raise ValueError("invalid worker coverage execution_status")
    count = max(0, int(relevant_signal_count))
    legacy_status = {"complete": "ok", "partial": "partial", "failed": "failed", "skipped": "partial"}[execution_status]
    return CoverageRecord(
        {
            "run_key": run_key,
            "source_id": source_id,
            "source_name": source_name,
            "source_group": source_group,
            "route": route,
            "status": legacy_status,
            "hit_count": count,
            "representative_url": representative_url,
            "failure_reason": failure_reason,
            "checked_at_bjt": checked_at_bjt,
            "fallback_used": "TRUE" if fallback_used else "FALSE",
            "notes": notes,
            "retrieval_status": execution_status if execution_status != "skipped" else "partial",
            "hit_status": "hit" if count else "no_hit",
            "coverage_id": make_coverage_id(run_key, producer_id, attempt_id, channel_id, route_id, source_id),
            "attempt_id": attempt_id,
            "producer_id": producer_id,
            "channel_id": channel_id,
            "route_id": route_id,
            "execution_status": execution_status,
            "saturation_status": saturation_status,
            "results_seen": results_seen,
            "relevant_signal_count": count,
            "schema_version": "v11.0",
        }
    )


def required_worker_routes(cfg: Mapping[str, object], entity_rows: Iterable[Mapping[str, object]]) -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {channel: set() for channel in ("C1", "C2", "C4", "C6")}
    plan_map = cfg.get("worker_channel_plan_map_json", {}) or {}
    for channel in ("C1", "C4", "C6"):
        for plan_id in plan_map.get(channel, []):
            routes[channel].add(f"worker/plan/{plan_id}")

    broad_count = int(float(cfg.get("c1_required_broad_query_count", 0) or 0))
    for idx in range(1, broad_count + 1):
        routes["C1"].add(f"worker/c1/broad/{idx:02d}")
    for key in ("c1_premium_sources_json", "c1_specialist_sources_json"):
        for source_id in cfg.get(key, []) or []:
            routes["C1"].add(f"worker/source/{source_id}")

    for row in entity_rows:
        if str(row.get("status", "")).strip().lower() != "active":
            continue
        if str(row.get("priority", "")).strip() != "P0":
            continue
        entity_id = str(row.get("entity_id", "")).strip()
        if entity_id:
            routes["C2"].add(f"worker/entity/{entity_id}")
    return routes


def _coverage_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("producer_id", "")).strip(),
        str(row.get("channel_id", "")).strip(),
        str(row.get("route_id", "")).strip(),
    )


def structured_snapshot_fingerprint(
    *,
    run_key: str,
    attempt_id: str,
    active_signals: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
) -> str:
    """Fingerprint one persisted Structured snapshot for isolated replay.

    The fingerprint locks both active ``collector/*`` Signal rows and their
    Structured Coverage rows. It is intentionally scoped to one run/attempt so
    a manual diagnostic replay can reference an immutable scheduled input
    without cloning those rows into the manual namespace.
    """
    signal_lines: list[str] = []
    for row in active_signals:
        if _text(row.get("run_key")) != run_key:
            continue
        if _text(row.get("origin_attempt_id")) != attempt_id:
            continue
        if _text(row.get("signal_state")) != "active":
            continue
        if not _text(row.get("producer_id")).startswith("collector/"):
            continue
        signal_lines.append("S|" + "\x1f".join(_text(row.get(header)) for header in SIGNAL_HEADERS))

    coverage_lines: list[str] = []
    for row in coverage_rows:
        if _text(row.get("run_key")) != run_key:
            continue
        if _text(row.get("attempt_id")) != attempt_id:
            continue
        if not _text(row.get("producer_id")).startswith("collector/"):
            continue
        coverage_lines.append("C|" + "\x1f".join(_text(row.get(header)) for header in COVERAGE_HEADERS))

    payload = "\n".join(sorted(signal_lines) + sorted(coverage_lines)).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _authorized_frozen_structured_signals(
    *,
    run_key: str,
    active_signals: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
    frozen_structured_run_key: str,
    frozen_structured_attempt_id: str,
    frozen_structured_fingerprint: str,
) -> tuple[dict[str, Mapping[str, object]], list[str]]:
    """Return the only cross-run Signals an isolated manual replay may consume.

    Authorization is fail-closed: it must be explicit, originate from the
    scheduled Shadow namespace on the same report date, match one qualified
    attempt and fingerprint, and include only active Structured collector
    Signals. Worker/Rescue rows from the source run are never imported.
    """
    requested = any(
        _text(value)
        for value in (
            frozen_structured_run_key,
            frozen_structured_attempt_id,
            frozen_structured_fingerprint,
        )
    )
    if not requested:
        return {}, []

    errors: list[str] = []
    source_run = _text(frozen_structured_run_key)
    source_attempt = _text(frozen_structured_attempt_id)
    expected_fingerprint = _text(frozen_structured_fingerprint)

    if not all((source_run, source_attempt, expected_fingerprint)):
        return {}, ["frozen_structured_input_incomplete"]
    if not SHADOW_RUN_RE.match(run_key) or not run_key.startswith("AILS11M-"):
        errors.append("frozen_structured_input_requires_manual_shadow")
    if not SHADOW_RUN_RE.match(source_run) or not source_run.startswith("AILS11S-"):
        errors.append("frozen_structured_source_not_scheduled_shadow")
    if _date_token(run_key) != _date_token(source_run):
        errors.append("frozen_structured_report_date_mismatch")
    if not source_attempt.startswith(f"{source_run}-A"):
        errors.append("frozen_structured_attempt_not_qualified")

    source_rows = [
        row
        for row in active_signals
        if _text(row.get("run_key")) == source_run
        and _text(row.get("origin_attempt_id")) == source_attempt
        and _text(row.get("signal_state")) == "active"
        and _text(row.get("producer_id")).startswith("collector/")
    ]
    source_coverage = [
        row
        for row in coverage_rows
        if _text(row.get("run_key")) == source_run
        and _text(row.get("attempt_id")) == source_attempt
        and _text(row.get("producer_id")).startswith("collector/")
    ]
    if not source_rows:
        errors.append("frozen_structured_input_has_no_active_signals")
    if not source_coverage:
        errors.append("frozen_structured_input_has_no_coverage")

    actual_fingerprint = structured_snapshot_fingerprint(
        run_key=source_run,
        attempt_id=source_attempt,
        active_signals=source_rows,
        coverage_rows=source_coverage,
    )
    if expected_fingerprint != actual_fingerprint:
        errors.append("frozen_structured_snapshot_fingerprint_mismatch")

    by_id: dict[str, Mapping[str, object]] = {}
    for row in source_rows:
        signal_id = _text(row.get("signal_id"))
        if not signal_id:
            errors.append("frozen_structured_signal_id_missing")
            continue
        if signal_id in by_id:
            errors.append("frozen_structured_duplicate_signal_id")
            continue
        by_id[signal_id] = row

    if errors:
        return {}, sorted(set(errors))
    return by_id, []


def validate_unified_ingestion_snapshot(
    *,
    run_key: str,
    attempt_id: str,
    active_signals: Iterable[Mapping[str, object]],
    candidates: Iterable[Mapping[str, object]],
    coverage_rows: Iterable[Mapping[str, object]],
    required_routes: Mapping[str, set[str]],
    channel_health: Mapping[str, str] | None = None,
    frozen_structured_run_key: str = "",
    frozen_structured_attempt_id: str = "",
    frozen_structured_fingerprint: str = "",
) -> list[str]:
    errors: list[str] = []
    signals = list(active_signals)
    candidates = list(candidates)
    coverage = list(coverage_rows)
    channel_health = channel_health or {}

    current_active_by_id = {
        str(row.get("signal_id", "")).strip(): row
        for row in signals
        if str(row.get("run_key", "")).strip() == run_key
        and str(row.get("signal_state", "")).strip() == "active"
        and str(row.get("signal_id", "")).strip()
    }
    frozen_active_by_id, frozen_errors = _authorized_frozen_structured_signals(
        run_key=run_key,
        active_signals=signals,
        coverage_rows=coverage,
        frozen_structured_run_key=frozen_structured_run_key,
        frozen_structured_attempt_id=frozen_structured_attempt_id,
        frozen_structured_fingerprint=frozen_structured_fingerprint,
    )
    errors.extend(frozen_errors)

    active_by_id = dict(current_active_by_id)
    if not frozen_errors:
        for signal_id, row in frozen_active_by_id.items():
            # Preserve the current-run row if a stable same-day Signal ID is
            # independently rediscovered during the manual Worker replay.
            active_by_id.setdefault(signal_id, row)

    worker_signals = [
        row
        for row in current_active_by_id.values()
        if str(row.get("producer_id", "")).strip() in WORKER_PRODUCERS
        and str(row.get("origin_attempt_id", "")).strip() == attempt_id
    ]
    worker_coverage = [
        row
        for row in coverage
        if str(row.get("run_key", "")).strip() == run_key
        and str(row.get("attempt_id", "")).strip() == attempt_id
        and str(row.get("producer_id", "")).strip() in WORKER_PRODUCERS
    ]

    coverage_by_route: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    coverage_ids: set[str] = set()
    for row in worker_coverage:
        channel = str(row.get("channel_id", "")).strip()
        route = str(row.get("route_id", "")).strip()
        if not channel or not route:
            errors.append("worker_coverage_missing_channel_or_route")
            continue
        coverage_by_route.setdefault((channel, route), []).append(row)
        cid = str(row.get("coverage_id", "")).strip()
        if cid:
            if cid in coverage_ids:
                errors.append("duplicate_worker_coverage_id")
            coverage_ids.add(cid)
        expected = make_coverage_id(
            run_key,
            str(row.get("producer_id", "")).strip(),
            attempt_id,
            channel,
            route,
            str(row.get("source_id", "")).strip(),
        )
        if cid and cid != expected:
            errors.append("worker_coverage_id_mismatch")

    for channel, routes in required_routes.items():
        for route in routes:
            matches = coverage_by_route.get((channel, route), [])
            if not matches:
                errors.append(f"required_route_missing:{channel}")
                continue
            if str(channel_health.get(channel, "")).strip() == "complete":
                if not any(str(row.get("execution_status", "")).strip() == "complete" for row in matches):
                    errors.append(f"complete_channel_has_degraded_route:{channel}")

    signal_routes = {
        (
            str(row.get("producer_id", "")).strip(),
            str(row.get("channel_id", "")).strip(),
            str(row.get("route_id", "")).strip(),
        )
        for row in worker_signals
    }
    for row in worker_signals:
        if not str(row.get("route_id", "")).strip():
            errors.append("worker_signal_missing_route_id")
        if str(row.get("schema_version", "")).strip() != "v11.0":
            errors.append("worker_signal_schema_version_not_v11")
        if not str(row.get("url", "")).strip() or not str(row.get("raw_title", "")).strip():
            errors.append("worker_signal_missing_title_or_url")
        route_matches = coverage_by_route.get(
            (str(row.get("channel_id", "")).strip(), str(row.get("route_id", "")).strip()), []
        )
        if not route_matches:
            errors.append("worker_signal_without_coverage_route")

    for row in worker_coverage:
        try:
            count = int(float(str(row.get("relevant_signal_count", "0") or "0")))
        except ValueError:
            count = -1
        if count > 0 and _coverage_key(row) not in signal_routes:
            errors.append("worker_coverage_hit_without_active_signal")

    for candidate in candidates:
        for signal_id in parse_signal_ids(candidate.get("source_signal_ids")):
            if signal_id not in active_by_id:
                errors.append("candidate_references_nonactive_signal")

    return sorted(set(errors))


def compact_manifest_hash(required_routes: Mapping[str, set[str]]) -> str:
    payload = "\n".join(
        f"{channel}|{route}"
        for channel in sorted(required_routes)
        for route in sorted(required_routes[channel])
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
