from __future__ import annotations

import json
from urllib.parse import urlencode

from ails_intel.http_client import HttpClient
from ails_intel.safe_logger import log_event


EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _server_for_collector(collector_id: str) -> str:
    return {
        "COL-BIORXIV": "bioRxiv",
        "COL-MEDRXIV": "medRxiv",
    }.get(collector_id, "")


def europepmc_probe_url(collector_id: str, window) -> str:
    server = _server_for_collector(collector_id)
    if not server:
        return ""
    query = (
        f'SRC:PPR AND JOURNAL:"{server}" '
        f'AND FIRST_PDATE:[{window.start.isoformat()} TO {window.end.isoformat()}]'
    )
    params = {
        "query": query,
        "resultType": "core",
        "pageSize": "10",
        "format": "json",
        "sort": "FIRST_PDATE_D desc",
    }
    return f"{EUROPE_PMC_SEARCH_URL}?{urlencode(params)}"


def _probe_fields(payload: dict, server: str) -> dict[str, object]:
    results = ((payload.get("resultList") or {}).get("result") or [])
    server_lower = server.lower()
    return {
        "epmc_hit_count": int(payload.get("hitCount", 0) or 0),
        "epmc_result_count": len(results),
        "epmc_server_match_count": sum(
            1 for item in results if str(item.get("journalTitle", "")).strip().lower() == server_lower
        ),
        "epmc_doi_count": sum(1 for item in results if str(item.get("doi", "")).strip()),
        "epmc_title_count": sum(1 for item in results if str(item.get("title", "")).strip()),
        "epmc_abstract_count": sum(1 for item in results if str(item.get("abstractText", "")).strip()),
        "epmc_date_count": sum(1 for item in results if str(item.get("firstPublicationDate", "")).strip()),
    }


def run_europepmc_probe(spec, window, *, timeout: float) -> None:
    server = _server_for_collector(spec.collector_id)
    url = europepmc_probe_url(spec.collector_id, window)
    if not url:
        return
    http = HttpClient(timeout=timeout, retries=0)
    try:
        text = http.text(url)
        payload = json.loads(text)
        fields = _probe_fields(payload, server)
        result_count = int(fields["epmc_result_count"])
        server_matches = int(fields["epmc_server_match_count"])
        usable = result_count > 0 and server_matches == result_count
        log_event(
            "collector_diagnostic_probe",
            component="collector_diagnostics",
            stage="europepmc_preprint_probe",
            status="PASS" if usable else "DEGRADED",
            collector_id=spec.collector_id,
            source_id=spec.source_id,
            channel_id=spec.channel_id,
            execution_status="complete" if usable else "partial",
            error_code="" if usable else "NO_SERVER_MATCHED_RESULTS",
            **http.diagnostic_log_fields(),
            **fields,
        )
    except Exception as exc:
        log_event(
            "collector_diagnostic_probe",
            component="collector_diagnostics",
            stage="europepmc_preprint_probe",
            status="DEGRADED",
            collector_id=spec.collector_id,
            source_id=spec.source_id,
            channel_id=spec.channel_id,
            execution_status="failed",
            error_code=type(exc).__name__,
            **http.diagnostic_log_fields(),
        )
