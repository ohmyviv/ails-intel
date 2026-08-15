from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.diagnostic_probes import (
    _probe_fields,
    _probe_usable,
    europepmc_probe_url,
    europepmc_probe_urls,
)


def test_europepmc_probe_targets_biorxiv_and_date_window():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    targets = europepmc_probe_urls("COL-BIORXIV", window)
    assert [stage for stage, _ in targets] == [
        "europepmc_current_server_probe",
        "europepmc_current_ppr_probe",
        "europepmc_known_record_probe",
    ]
    current_url = targets[0][1]
    assert "europepmc/webservices/rest/search" in current_url
    assert "JOURNAL%3A%22bioRxiv%22" in current_url
    assert "FIRST_PDATE%3A%5B2026-08-08+TO+2026-08-15%5D" in current_url
    assert "resultType=core" in current_url
    assert "format=json" in current_url
    assert "DOI%3A%2210.1101%2F2025.02.13.638084%22" in targets[2][1]


def test_europepmc_probe_targets_medrxiv_and_known_control():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    targets = europepmc_probe_urls("COL-MEDRXIV", window)
    assert "JOURNAL%3A%22medRxiv%22" in targets[0][1]
    assert "DOI%3A%2210.1101%2F2021.01.22.21250054%22" in targets[2][1]


def test_europepmc_compatibility_url_returns_server_probe():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    assert europepmc_probe_url("COL-BIORXIV", window) == europepmc_probe_urls("COL-BIORXIV", window)[0][1]


def test_europepmc_probe_rejects_unrelated_collector():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    assert europepmc_probe_url("COL-PUBMED", window) == ""
    assert europepmc_probe_urls("COL-PUBMED", window) == []


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
    fields = _probe_fields(payload, "bioRxiv")
    assert fields == {
        "epmc_hit_count": 12,
        "epmc_result_count": 2,
        "epmc_server_match_count": 2,
        "epmc_doi_count": 2,
        "epmc_title_count": 2,
        "epmc_abstract_count": 1,
        "epmc_date_count": 2,
    }
    assert _probe_usable("europepmc_current_server_probe", fields)
    assert _probe_usable("europepmc_current_ppr_probe", fields)
    assert _probe_usable("europepmc_known_record_probe", fields)


def test_broad_ppr_probe_only_requires_results_not_server_match():
    fields = {
        "epmc_result_count": 5,
        "epmc_server_match_count": 0,
    }
    assert _probe_usable("europepmc_current_ppr_probe", fields)
    assert not _probe_usable("europepmc_current_server_probe", fields)
