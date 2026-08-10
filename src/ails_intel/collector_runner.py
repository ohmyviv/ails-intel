from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_service, spreadsheet_id_from_env
from ails_intel.collectors.arxiv import ArxivCollector
from ails_intel.collectors.base import Window
from ails_intel.collectors.biorxiv import BiorxivCollector
from ails_intel.collectors.clinicaltrials import ClinicalTrialsCollector
from ails_intel.collectors.pubmed import PubMedCollector
from ails_intel.collectors.rss import RssCollector
from ails_intel.http_client import HttpClient
from ails_intel.models import CoverageRecord, SignalRecord
from ails_intel.runtime import build_run_key, collector_specs, collector_window_days, load_active_config, load_source_specs
from ails_intel.safe_logger import log_event
from ails_intel.signal_keys import make_coverage_id, make_signal_id, make_signal_key
from ails_intel.state.sheets import SheetsStore

FIXED_COLLECTOR_IDS = {"COL-PUBMED", "COL-ARXIV", "COL-BIORXIV", "COL-MEDRXIV", "COL-CTGOV"}
DIAGNOSTIC_INVALIDATION_NOTE = "diagnostic_first_run_pre_sprint2.1"


def _now(tz_name: str):
    return datetime.now(ZoneInfo(tz_name))


def _is_rss_spec(spec) -> bool:
    return str(spec.options.get("kind", "")).strip().lower() == "rss"


def _collector_supported(spec) -> bool:
    return spec.collector_id in FIXED_COLLECTOR_IDS or _is_rss_spec(spec)


def _build_collector(spec, *, prior_signals=None):
    gate_options = spec.options.get("relevance_gate")
    gate_options = dict(gate_options) if isinstance(gate_options, dict) else {}
    if spec.collector_id == "COL-PUBMED":
        return PubMedCollector(gate_options=gate_options)
    if spec.collector_id == "COL-ARXIV":
        return ArxivCollector()
    if spec.collector_id == "COL-BIORXIV":
        return BiorxivCollector("biorxiv")
    if spec.collector_id == "COL-MEDRXIV":
        return BiorxivCollector("medrxiv")
    if spec.collector_id == "COL-CTGOV":
        return ClinicalTrialsCollector(gate_options=gate_options, prior_signals=prior_signals or {})
    if _is_rss_spec(spec):
        return RssCollector(
            feed_url=str(spec.options.get("feed_url", "")),
            relevance_query=str(spec.options.get("relevance_query", "")),
        )
    raise KeyError(spec.collector_id)


def signal_priority_for_channel(channel_id: str) -> str:
    # SourceRegistry priority describes scan importance, not event severity.
    # Hard/clinical/product/regional discovery starts at P1; technical frontier
    # starts at P2. Source-specific deterministic gates may demote a weaker C3
    # record to P2 before the reasoning worker sees it.
    return "P2" if channel_id == "C5" else "P1"


def existing_signal_action(record: dict[str, object] | None) -> str:
    if record is None:
        return "new"
    state = str(record.get("state", "")).strip()
    notes = str(record.get("notes", "")).strip()
    if state == "invalid" and notes == DIAGNOSTIC_INVALIDATION_NOTE:
        return "reactivate"
    return "duplicate"


def _signal(
    item,
    *,
    run_key,
    batch_id,
    producer_id,
    channel_id,
    route_id,
    source_id,
    discovery_method,
    discovered_at,
    date_token,
):
    key = make_signal_key(source_id, item.stable_id, item.url, item.title, item.published_date)
    priority = str(getattr(item, "priority_hint", "") or "").strip() or signal_priority_for_channel(channel_id)
    notes = str(getattr(item, "notes", "") or "").strip()
    return key, SignalRecord({
        "signal_id": make_signal_id(date_token, key), "run_key": run_key,
        "collection_batch_id": batch_id, "producer_id": producer_id, "origin_attempt_id": "",
        "discovered_at_bjt": discovered_at, "channel_id": channel_id,
        "route_id": route_id, "source_id": source_id,
        "discovery_method": discovery_method, "raw_title": item.title, "raw_snippet": item.snippet,
        "entity_hint": "", "action_hint": "", "asset_hint": "",
        "event_date_hint": item.event_date, "published_at_hint": item.published_date,
        "first_public_at_hint": item.first_public_at, "url": item.url, "stable_id": item.stable_id,
        "signal_key": key, "event_key_hint": "",
        "priority_hint": priority,
        "ai_core_hint": "TRUE", "life_science_core_hint": "TRUE",
        "signal_state": "active", "notes": notes, "schema_version": "v11.0",
    })


def _legacy_status(execution_status: str) -> str:
    return {"complete": "ok", "partial": "partial", "failed": "failed"}.get(execution_status, execution_status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collector", action="append", help="Run only the named collector; repeatable")
    args = parser.parse_args()

    started = time.monotonic()
    service = build_sheets_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    cfg = load_active_config(store)

    execution_mode = str(cfg["execution_mode"].value)
    if execution_mode not in {"shadow", "production"}:
        log_event("structured_collectors", component="collector_runner", status="FAIL", error_code="INVALID_EXECUTION_MODE")
        raise SystemExit(1)
    if not bool(cfg["collector_write_signals_enabled"].value):
        log_event("structured_collectors", component="collector_runner", status="FAIL", error_code="COLLECTOR_WRITES_DISABLED")
        raise SystemExit(1)

    now = _now(str(cfg["timezone"].value))
    run_key = build_run_key(cfg, now)
    specs = collector_specs(cfg)
    configured_ids = {s.collector_id for s in specs}
    unsupported = {s.collector_id for s in specs if not _collector_supported(s)}
    if unsupported:
        log_event("structured_collectors", component="collector_runner", status="FAIL", run_key=run_key, error_code="UNSUPPORTED_CONFIGURED_COLLECTOR", error_count=len(unsupported))
        raise SystemExit(1)
    if args.collector:
        wanted = set(args.collector)
        unknown_requested = wanted - configured_ids
        if unknown_requested:
            log_event("structured_collectors", component="collector_runner", status="FAIL", run_key=run_key, error_code="UNKNOWN_REQUESTED_COLLECTOR", error_count=len(unknown_requested))
            raise SystemExit(1)
        specs = [s for s in specs if s.collector_id in wanted]

    sources = load_source_specs(store, {s.source_id for s in specs})
    limits = cfg["collector_limits_json"].value
    timeout = float(cfg["collector_timeout_seconds"].value)
    retries = int(float(cfg["collector_retry_limit"].value))
    http = HttpClient(timeout=timeout, retries=retries)
    existing_records = store.signal_key_records(run_key)

    coverage = []
    all_new = []
    reactivation_updates: list[tuple[int, str]] = []
    total_duplicates = 0
    total_reactivated = 0
    for spec in specs:
        prior_signals = {}
        if spec.collector_id == "COL-CTGOV":
            prior_signals = store.latest_source_signals(spec.source_id, exclude_run_key=run_key)
        collector = _build_collector(spec, prior_signals=prior_signals)
        source = sources[spec.source_id]
        max_results = int(limits.get(spec.collector_id, cfg["collector_default_max_results"].value))
        configured_days = spec.options.get("window_days", "")
        days = int(float(configured_days)) if str(configured_days).strip() else collector_window_days(cfg, spec.channel_id)
        window = Window(start=(now.date() - timedelta(days=days)), end=now.date())
        producer_id = f"collector/{spec.collector_id}"
        is_rss = _is_rss_spec(spec)
        route_kind = "rss" if is_rss else "api"
        route_id = f"{route_kind}/{spec.collector_id}"
        batch_id = f"COL-{now:%Y%m%d-%H%M}-BJT-{spec.collector_id}"
        checked_at = now.isoformat(timespec="seconds")

        try:
            outcome = collector.collect(source=source, window=window, max_results=max_results, http=http)
        except Exception as exc:
            failure_reason = type(exc).__name__
            coverage.append(CoverageRecord({
                "run_key": run_key, "source_id": spec.source_id, "source_name": source.source_name,
                "source_group": "structured", "route": route_kind, "status": "failed", "hit_count": 0,
                "representative_url": "", "failure_reason": failure_reason, "checked_at_bjt": checked_at,
                "fallback_used": "FALSE", "notes": "", "retrieval_status": "failed", "hit_status": "no_hit",
                "coverage_id": make_coverage_id(run_key, producer_id, "", spec.channel_id, route_id, spec.source_id),
                "attempt_id": "", "producer_id": producer_id, "channel_id": spec.channel_id, "route_id": route_id,
                "execution_status": "failed", "saturation_status": "unknown", "results_seen": 0,
                "relevant_signal_count": 0, "schema_version": "v11.0",
            }))
            log_event("collector", component="collector_runner", status="FAIL", collector_id=spec.collector_id, source_id=spec.source_id, run_key=run_key, execution_status="failed", error_code=failure_reason)
            continue

        new_for_collector = []
        duplicates = 0
        reactivated = 0
        for item in outcome.relevant_items:
            effective_priority = str(getattr(item, "priority_hint", "") or "").strip() or signal_priority_for_channel(spec.channel_id)
            key, signal = _signal(
                item, run_key=run_key, batch_id=batch_id, producer_id=producer_id,
                channel_id=spec.channel_id, route_id=route_id, source_id=spec.source_id,
                discovery_method=route_kind, discovered_at=checked_at, date_token=now.strftime("%Y%m%d"),
            )
            record = existing_records.get(key)
            action = existing_signal_action(record)
            if action == "duplicate":
                duplicates += 1
                continue
            if action == "reactivate":
                row_idx = int(record["row"])
                reactivation_updates.append((row_idx, effective_priority))
                record["state"] = "active"
                record["notes"] = "revalidated_after_sprint2.1"
                reactivated += 1
                continue

            existing_records[key] = {"row": 0, "state": "active", "notes": str(getattr(item, "notes", "") or "")}
            new_for_collector.append(signal)

        all_new.extend(new_for_collector)
        total_duplicates += duplicates
        total_reactivated += reactivated

        hit_count = len(outcome.relevant_items)
        coverage.append(CoverageRecord({
            "run_key": run_key, "source_id": spec.source_id, "source_name": source.source_name,
            "source_group": "structured", "route": route_kind, "status": _legacy_status(outcome.execution_status),
            "hit_count": hit_count, "representative_url": outcome.representative_url,
            "failure_reason": outcome.failure_reason, "checked_at_bjt": checked_at,
            "fallback_used": "FALSE", "notes": outcome.diagnostic_note, "retrieval_status": outcome.execution_status,
            "hit_status": "hit" if hit_count else "no_hit",
            "coverage_id": make_coverage_id(run_key, producer_id, "", spec.channel_id, route_id, spec.source_id),
            "attempt_id": "", "producer_id": producer_id, "channel_id": spec.channel_id, "route_id": route_id,
            "execution_status": outcome.execution_status, "saturation_status": outcome.saturation_status,
            "results_seen": outcome.results_seen, "relevant_signal_count": hit_count, "schema_version": "v11.0",
        }))
        log_event(
            "collector", component="collector_runner", status="PASS" if outcome.execution_status != "failed" else "FAIL",
            collector_id=spec.collector_id, source_id=spec.source_id, run_key=run_key,
            execution_status=outcome.execution_status, saturation_status=outcome.saturation_status,
            results_seen=outcome.results_seen, signal_count=len(new_for_collector), duplicate_count=duplicates,
            reactivated_count=reactivated, collection_batch_id=batch_id,
        )

    store.reactivate_diagnostic_signals(reactivation_updates)
    store.append_signals(all_new)
    store.upsert_coverage(coverage)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    failed = sum(1 for r in coverage if r.values.get("execution_status") == "failed")
    log_event(
        "structured_collectors", component="collector_runner",
        status="PASS" if failed == 0 else "FAIL", run_key=run_key,
        signal_count=len(all_new), duplicate_count=total_duplicates,
        reactivated_count=total_reactivated, error_count=failed, elapsed_ms=elapsed_ms,
    )
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
