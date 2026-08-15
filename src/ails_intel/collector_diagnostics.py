from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_readonly_service, spreadsheet_id_from_env
from ails_intel.collector_runner import _build_collector, _collector_supported, _is_rss_spec
from ails_intel.collectors.base import Window
from ails_intel.http_client import HttpClient
from ails_intel.runtime import collector_specs, collector_window_days, load_active_config, load_source_specs
from ails_intel.safe_logger import log_event
from ails_intel.state.sheets import SheetsStore

DEFAULT_DIAGNOSTIC_COLLECTORS = (
    "COL-HITNEWS-AI",
    "COL-BIORXIV",
    "COL-MEDRXIV",
    "COL-FIERCE-RSS",
    "COL-PUBMED",
)


def _now(tz_name: str):
    return datetime.now(ZoneInfo(tz_name))


def select_specs(specs, requested: list[str] | None):
    configured = {spec.collector_id: spec for spec in specs}
    if not requested:
        wanted = [collector_id for collector_id in DEFAULT_DIAGNOSTIC_COLLECTORS if collector_id in configured]
    elif len(requested) == 1 and requested[0].strip().lower() == "all":
        wanted = [spec.collector_id for spec in specs]
    else:
        wanted = []
        seen = set()
        for raw in requested:
            collector_id = raw.strip()
            if not collector_id or collector_id in seen:
                continue
            seen.add(collector_id)
            wanted.append(collector_id)

    unknown = [collector_id for collector_id in wanted if collector_id not in configured]
    if unknown:
        raise ValueError(f"unknown collector ids: {unknown}")
    return [configured[collector_id] for collector_id in wanted]


def _diagnostic_fields(http: HttpClient) -> dict[str, object]:
    fields = http.diagnostic_log_fields()
    if int(fields.get("attempt_count", 0) or 0) <= 1:
        return {}
    return fields


def main():
    parser = argparse.ArgumentParser(description="Read-only structured collector diagnostics")
    parser.add_argument("--collector", action="append", help="Collector ID; repeatable. Use 'all' for every enabled collector.")
    args = parser.parse_args()

    started = time.monotonic()
    service = build_sheets_readonly_service()
    store = SheetsStore(service, spreadsheet_id_from_env())
    cfg = load_active_config(store)
    specs = collector_specs(cfg)

    unsupported = {spec.collector_id for spec in specs if not _collector_supported(spec)}
    if unsupported:
        log_event(
            "collector_diagnostics",
            component="collector_diagnostics",
            status="FAIL",
            error_code="UNSUPPORTED_CONFIGURED_COLLECTOR",
            error_count=len(unsupported),
        )
        raise SystemExit(1)

    try:
        specs = select_specs(specs, args.collector)
    except ValueError:
        log_event(
            "collector_diagnostics",
            component="collector_diagnostics",
            status="FAIL",
            error_code="UNKNOWN_REQUESTED_COLLECTOR",
        )
        raise SystemExit(2)

    if not specs:
        log_event(
            "collector_diagnostics",
            component="collector_diagnostics",
            status="FAIL",
            error_code="NO_DIAGNOSTIC_COLLECTORS",
        )
        raise SystemExit(2)

    sources = load_source_specs(store, {spec.source_id for spec in specs})
    limits = cfg["collector_limits_json"].value
    timeout = float(cfg["collector_timeout_seconds"].value)
    retries = int(float(cfg["collector_retry_limit"].value))
    http = HttpClient(timeout=timeout, retries=retries)
    now = _now(str(cfg["timezone"].value))

    failed = 0
    degraded = 0
    for spec in specs:
        prior_signals = {}
        if spec.collector_id == "COL-CTGOV":
            prior_signals = store.latest_source_signals(spec.source_id)
        collector = _build_collector(spec, prior_signals=prior_signals)
        source = sources[spec.source_id]
        max_results = int(limits.get(spec.collector_id, cfg["collector_default_max_results"].value))
        configured_days = spec.options.get("window_days", "")
        days = int(float(configured_days)) if str(configured_days).strip() else collector_window_days(cfg, spec.channel_id)
        window = Window(start=(now.date() - timedelta(days=days)), end=now.date())
        route_kind = "rss" if _is_rss_spec(spec) else "api"

        http.clear_diagnostic()
        try:
            outcome = collector.collect(source=source, window=window, max_results=max_results, http=http)
        except Exception as exc:
            failed += 1
            log_event(
                "collector_diagnostic",
                component="collector_diagnostics",
                status="DEGRADED",
                collector_id=spec.collector_id,
                source_id=spec.source_id,
                channel_id=spec.channel_id,
                execution_status="failed",
                error_code=type(exc).__name__,
                **http.diagnostic_log_fields(),
            )
            continue

        status = "PASS"
        if outcome.execution_status != "complete":
            status = "DEGRADED"
            degraded += 1
        log_event(
            "collector_diagnostic",
            component="collector_diagnostics",
            status=status,
            collector_id=spec.collector_id,
            source_id=spec.source_id,
            channel_id=spec.channel_id,
            execution_status=outcome.execution_status,
            saturation_status=outcome.saturation_status,
            results_seen=outcome.results_seen,
            signal_count=len(outcome.relevant_items),
            **_diagnostic_fields(http),
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    overall_status = "PASS" if failed == 0 and degraded == 0 else "DEGRADED"
    log_event(
        "collector_diagnostics",
        component="collector_diagnostics",
        status=overall_status,
        check_count=len(specs),
        error_count=failed,
        elapsed_ms=elapsed_ms,
    )

    # Source degradation is evidence, not a workflow integrity failure. The
    # diagnostic job exits zero so its logs remain available for automated
    # inspection and re-run. Configuration or invocation errors still fail.
    raise SystemExit(0)


if __name__ == "__main__":
    main()
