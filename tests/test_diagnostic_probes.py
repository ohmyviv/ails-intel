from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.diagnostic_probes import _probe_fields, europepmc_probe_url


def test_europepmc_probe_targets_biorxiv_and_date_window():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    url = europepmc_probe_url("COL-BIORXIV", window)
    assert "europepmc/webservices/rest/search" in url
    assert "JOURNAL%3A%22bioRxiv%22" in url
    assert "FIRST_PDATE%3A%5B2026-08-08+TO+2026-08-15%5D" in url
    assert "resultType=core" in url
    assert "format=json" in url


def test_europepmc_probe_targets_medrxiv():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    url = europepmc_probe_url("COL-MEDRXIV", window)
    assert "JOURNAL%3A%22medRxiv%22" in url


def test_europepmc_probe_rejects_unrelated_collector():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    assert europepmc_probe_url("COL-PUBMED", window) == ""


def test_probe_fields_only_returns_safe_counts():
    payload = {
        "hitCount": 12,
        "resultList": {
            "result": [
                {
                    "journalTitle": "bioRxiv",
                    "doi": "10.1101/example",
                    "title": "Example",
                    "abstractText": "Abstract",
                    "firstPublicationDate": "2026-08-15",
                },
                {
                    "journalTitle": "bioRxiv",
                    "doi": "10.1101/example2",
                    "title": "Example 2",
                    "firstPublicationDate": "2026-08-14",
                },
            ]
        },
    }
    assert _probe_fields(payload, "bioRxiv") == {
        "epmc_hit_count": 12,
        "epmc_result_count": 2,
        "epmc_server_match_count": 2,
        "epmc_doi_count": 2,
        "epmc_title_count": 2,
        "epmc_abstract_count": 1,
        "epmc_date_count": 2,
    }
