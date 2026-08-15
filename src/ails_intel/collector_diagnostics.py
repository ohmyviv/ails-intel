from __future__ import annotations

import argparse
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ails_intel.auth import build_sheets_readonly_service, spreadsheet_id_from_env
from ails_intel.collector_runner import _build_collector, _collector_supported
from ails_intel.collectors.base import Window
from ails_intel.collectors.rss import _date as rss_date
from ails_intel.collectors.rss import _link as rss_link
from ails_intel.collectors.rss import _text as rss_text
from ails_intel.diagnostic_probes import run_europepmc_probe
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


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _date_shape(value: str) -> str:
    shaped = re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", value or ""))
    return shaped[:120]


def _xml_structure_fields(text: str) -> dict[str, object]:
    root = ET.fromstring(text)
    names = [_local_name(node.tag) for node in root.iter()]
    feed_nodes = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    title_count = 0
    link_count = 0
    date_count = 0
    complete_count = 0
    first_date_raw = ""
    for node in feed_nodes:
        date_raw = rss_text(node, {"pubdate", "published", "updated", "date"})
        if not first_date_raw and date_raw:
            first_date_raw = date_raw
        has_title = bool(rss_text(node, {"title"}).strip())
        has_link = bool(rss_link(node).strip())
        has_date = bool(rss_date(date_raw))
        title_count += int(has_title)
        link_count += int(has_link)
        date_count += int(has_date)
        complete_count += int(has_title and has_link and has_date)
    child_tags = ""
    if feed_nodes:
        child_tags = ",".join(sorted({_local_name(child.tag) for child in list(feed_nodes[0])}))
    return {
        "root_tag": _local_name(root.tag),
        "item_count": names.count("item"),
        "entry_count": names.count("entry"),
        "channel_count": names.count("channel"),
        "title_count": title_count,
        "link_count": link_count,
        "date_count": date_count,
        "complete_count": complete_count,
        "child_tags": child_tags,
        "date_shape": _date_shape(first_date_raw),
        "date_length": len(first_date_raw),
    }


def diagnostic_probe_targets(spec, window: Window) -> list[tuple[str, str]]:
    """Return safe read-only probes for known structured-source failure modes."""
    if spec.collector_id == "COL-HITNEWS-AI":
        feed_url = str(spec.options.get("feed_url", "")).strip()
        if feed_url:
            return [("html_topic_probe", feed_url.split("?", 1)[0])]
        return []

    if spec.collector_id == "COL-FIERCE-RSS":
        feed_url = str(spec.options.get("feed_url", "")).strip()
        targets = []
        if feed_url:
            targets.append(("configured_feed_probe", feed_url))
        all_feed = "https://www.fiercebiotech.com/rss/xml"
        if all_feed != feed_url:
            targets.append(("all_stories_feed_probe", all_feed))
        return targets

    server = {
        "COL-BIORXIV": "biorxiv",
        "COL-MEDRXIV": "medrxiv",
    }.get(spec.collector_id)
    if server:
        base = f"https://api.biorxiv.org/details/{server}/{window.start.isoformat()}/{window.end.isoformat()}/0"
        return [
            ("explicit_json_probe", f"{base}/json"),
            ("explicit_xml_probe", f"{base}/xml"),
        ]
    return []


def run_failure_probes(spec, window: Window, *, timeout: float) -> None:
    for stage, url in diagnostic_probe_targets(spec, window):
        probe_http = HttpClient(timeout=timeout, retries=0)
        try:
            text = probe_http.text(url)
            fields = probe_http.diagnostic_log_fields()
            empty = int(fields.get("response_bytes", 0) or 0) == 0
            extra_fields: dict[str, object] = {}
            error_code = "EMPTY_BODY" if empty else ""
            status = "DEGRADED" if empty else "PASS"
            execution_status = "failed" if empty else "complete"
            if not empty and stage.endswith("feed_probe"):
                try:
                    extra_fields = _xml_structure_fields(text)
                    item_count = int(extra_fields.get("item_count", 0) or 0)
                    entry_count = int(extra_fields.get("entry_count", 0) or 0)
                    complete_count = int(extra_fields.get("complete_count", 0) or 0)
                    if item_count + entry_count == 0:
                        status = "DEGRADED"
                        execution_status = "partial"
                        error_code = "NO_FEED_ITEMS"
                    elif complete_count == 0:
                        status = "DEGRADED"
                        execution_status = "partial"
                        error_code = "NO_PARSEABLE_ITEMS"
                except ET.ParseError:
                    status = "DEGRADED"
                    execution_status = "failed"
                    error_code = "XML_PARSE_ERROR"
            log_event(
                "collector_diagnostic_probe",
                component="collector_diagnostics",
                stage=stage,
                status=status,
                collector_id=spec.collector_id,
                source_id=spec.source_id,
                channel_id=spec.channel_id,
                execution_status=execution_status,
                error_code=error_code,
                **fields,
                **extra_fields,
            )
        except Exception as exc:
            log_event(
                "collector_diagnostic_probe",
                component="collector_diagnostics",
                stage=stage,
                status="DEGRADED",
                collector_id=spec.collector_id,
                source_id=spec.source_id,
                channel_id=spec.channel_id,
                execution_status="failed",
                error_code=type(exc).__name__,
                **probe_http.diagnostic_log_fields(),
            )


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
            run_failure_probes(spec, window, timeout=timeout)
            if spec.collector_id in {"COL-BIORXIV", "COL-MEDRXIV"}:
                run_europepmc_probe(spec, window, timeout=timeout)
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
            error_code=outcome.failure_reason if outcome.execution_status != "complete" else "",
            **_diagnostic_fields(http),
        )
        if outcome.execution_status != "complete":
            run_failure_probes(spec, window, timeout=timeout)

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
