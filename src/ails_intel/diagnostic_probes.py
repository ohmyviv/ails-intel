from __future__ import annotations

import json
from urllib.parse import urlencode

from ails_intel.http_client import HttpClient
from ails_intel.safe_logger import log_event


EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
KNOWN_PREPRINT_DOIS = {
    "COL-BIORXIV": "10.1101/2025.02.13.638084",
    "COL-MEDRXIV": "10.1101/2021.01.22.21250054",
}
_TEXT_KEYS = {
    "title",
    "abstracttext",
    "authorstring",
    "affiliation",
    "affiliationtext",
    "keyword",
    "keywords",
}


def _server_for_collector(collector_id: str) -> str:
    return {
        "COL-BIORXIV": "bioRxiv",
        "COL-MEDRXIV": "medRxiv",
    }.get(collector_id, "")


def _search_url(query: str, *, page_size: int = 10) -> str:
    params = {
        "query": query,
        "resultType": "core",
        "pageSize": str(page_size),
        "format": "json",
        "sort": "FIRST_PDATE_D desc",
    }
    return f"{EUROPE_PMC_SEARCH_URL}?{urlencode(params)}"


def europepmc_probe_urls(collector_id: str, window) -> list[tuple[str, str]]:
    server = _server_for_collector(collector_id)
    if not server:
        return []
    date_clause = f"FIRST_PDATE:[{window.start.isoformat()} TO {window.end.isoformat()}]"
    known_doi = KNOWN_PREPRINT_DOIS[collector_id]
    return [
        (
            "europepmc_current_server_probe",
            _search_url(f'SRC:PPR AND JOURNAL:"{server}" AND {date_clause}', page_size=25),
        ),
        (
            "europepmc_current_ppr_probe",
            _search_url(f"SRC:PPR AND {date_clause}", page_size=100),
        ),
        (
            "europepmc_known_record_probe",
            _search_url(f'SRC:PPR AND DOI:"{known_doi}"', page_size=5),
        ),
    ]


def europepmc_probe_url(collector_id: str, window) -> str:
    """Compatibility helper returning the current server-filtered probe URL."""
    targets = europepmc_probe_urls(collector_id, window)
    return targets[0][1] if targets else ""


def _server_match_paths(value, server: str, *, path: str = "") -> set[str]:
    """Find metadata paths containing the preprint-server label without logging values."""
    matches: set[str] = set()
    server_lower = server.lower()
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text.lower() in _TEXT_KEYS:
                continue
            child_path = f"{path}.{key_text}" if path else key_text
            matches.update(_server_match_paths(child, server, path=child_path))
        return matches
    if isinstance(value, list):
        for child in value:
            matches.update(_server_match_paths(child, server, path=f"{path}[]"))
        return matches
    if isinstance(value, str) and server_lower in value.strip().lower():
        matches.add(path)
    return matches


def _probe_fields(payload: dict, server: str) -> dict[str, object]:
    results = ((payload.get("resultList") or {}).get("result") or [])
    matched_paths: set[str] = set()
    server_match_count = 0
    for item in results:
        paths = _server_match_paths(item, server)
        if paths:
            server_match_count += 1
            matched_paths.update(paths)
    result_keys = ",".join(sorted(str(key) for key in results[0].keys())) if results else ""
    return {
        "epmc_hit_count": int(payload.get("hitCount", 0) or 0),
        "epmc_result_count": len(results),
        "epmc_server_match_count": server_match_count,
        "epmc_doi_count": sum(1 for item in results if str(item.get("doi", "")).strip()),
        "epmc_title_count": sum(1 for item in results if str(item.get("title", "")).strip()),
        "epmc_abstract_count": sum(1 for item in results if str(item.get("abstractText", "")).strip()),
        "epmc_date_count": sum(1 for item in results if str(item.get("firstPublicationDate", "")).strip()),
        "epmc_result_keys": result_keys[:1200],
        "epmc_server_match_paths": ",".join(sorted(matched_paths))[:1200],
    }


def _probe_usable(stage: str, fields: dict[str, object]) -> bool:
    result_count = int(fields["epmc_result_count"])
    server_matches = int(fields["epmc_server_match_count"])
    if stage == "europepmc_current_ppr_probe":
        return result_count > 0
    return result_count > 0 and server_matches > 0


def run_europepmc_probe(spec, window, *, timeout: float) -> None:
    server = _server_for_collector(spec.collector_id)
    for stage, url in europepmc_probe_urls(spec.collector_id, window):
        http = HttpClient(timeout=timeout, retries=0)
        try:
            text = http.text(url)
            payload = json.loads(text)
            fields = _probe_fields(payload, server)
            usable = _probe_usable(stage, fields)
            log_event(
                "collector_diagnostic_probe",
                component="collector_diagnostics",
                stage=stage,
                status="PASS" if usable else "DEGRADED",
                collector_id=spec.collector_id,
                source_id=spec.source_id,
                channel_id=spec.channel_id,
                execution_status="complete" if usable else "partial",
                error_code="" if usable else "NO_MATCHED_RESULTS",
                **http.diagnostic_log_fields(),
                **fields,
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
                **http.diagnostic_log_fields(),
            )
