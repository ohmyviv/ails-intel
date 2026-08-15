import json
from datetime import date

import pytest

from ails_intel.collectors.base import Window
from ails_intel.collectors.biorxiv import BiorxivCollector
from ails_intel.models import SourceSpec


WINDOW = Window(date(2026, 8, 8), date(2026, 8, 15))


class FallbackHttp:
    def __init__(self, pages=None, *, fallback_error=None):
        self.pages = list(pages or [])
        self.fallback_error = fallback_error
        self.calls = []

    def json(self, url, params=None):
        self.calls.append((url, params))
        if "api.biorxiv.org" in url:
            raise json.JSONDecodeError("empty openRxiv body", "", 0)
        if "europepmc" in url:
            if self.fallback_error:
                raise self.fallback_error
            if not self.pages:
                raise AssertionError("unexpected Europe PMC page request")
            return self.pages.pop(0)
        raise AssertionError(url)


def _source(source_id="SRC-019", name="bioRxiv"):
    return SourceSpec(source_id, name, "P1", 'AI OR "virtual cell" OR "protein design"')


def _record(
    doi,
    *,
    publisher="bioRxiv",
    title="AI virtual cell foundation model",
    abstract="Artificial intelligence for protein design.",
    published="2026-08-15",
):
    return {
        "bookOrReportDetails": {"publisher": publisher},
        "doi": doi,
        "title": title,
        "abstractText": abstract,
        "firstPublicationDate": published,
    }


def test_biorxiv_falls_back_to_europepmc_and_stays_partial():
    http = FallbackHttp([
        {
            "hitCount": 2,
            "resultList": {"result": [
                _record("10.1101/a"),
                _record("10.1101/wrong", publisher="medRxiv"),
            ]},
        }
    ])
    out = BiorxivCollector("biorxiv").collect(
        source=_source(), window=WINDOW, max_results=10, http=http,
    )

    assert out.execution_status == "partial"
    assert out.saturation_status == "clear"
    assert out.fallback_used is True
    assert out.failure_reason == "native_openrxiv_failed_europepmc_fallback"
    assert out.results_seen == 2
    assert [item.stable_id for item in out.relevant_items] == ["10.1101/a"]
    item = out.relevant_items[0]
    assert item.url == "https://www.biorxiv.org/content/10.1101/a"
    assert item.published_date == "2026-08-15"
    assert item.first_public_at == "2026-08-15"
    assert "metadata_source=europepmc_fallback" in item.notes

    epmc_call = next((url, params) for url, params in http.calls if "europepmc" in url)
    assert 'PUBLISHER:"bioRxiv"' in epmc_call[1]["query"]
    assert "FIRST_PDATE:[2026-08-08 TO 2026-08-15]" in epmc_call[1]["query"]
    assert epmc_call[1]["pageSize"] == 1000
    assert epmc_call[1]["cursorMark"] == "*"


def test_medrxiv_fallback_preserves_medrxiv_attribution():
    http = FallbackHttp([
        {
            "hitCount": 1,
            "resultList": {"result": [_record("10.1101/m", publisher="medRxiv")]},
        }
    ])
    out = BiorxivCollector("medrxiv").collect(
        source=_source("SRC-020", "medRxiv"), window=WINDOW, max_results=10, http=http,
    )
    assert out.fallback_used is True
    assert out.relevant_items[0].url == "https://www.medrxiv.org/content/10.1101/m"
    epmc_call = next((url, params) for url, params in http.calls if "europepmc" in url)
    assert 'PUBLISHER:"medRxiv"' in epmc_call[1]["query"]


def test_europepmc_fallback_applies_local_relevance_and_required_fields():
    http = FallbackHttp([
        {
            "hitCount": 4,
            "resultList": {"result": [
                _record("10.1101/relevant"),
                _record("10.1101/unrelated", title="Wet lab microscopy", abstract="No computational work."),
                _record("", title="AI virtual cell"),
                _record("10.1101/nodate", published=""),
            ]},
        }
    ])
    out = BiorxivCollector("biorxiv").collect(
        source=_source(), window=WINDOW, max_results=10, http=http,
    )
    assert [item.stable_id for item in out.relevant_items] == ["10.1101/relevant"]
    assert out.results_seen == 4
    assert out.fallback_used is True


def test_europepmc_fallback_paginates_with_cursor_mark():
    http = FallbackHttp([
        {
            "hitCount": 2,
            "nextCursorMark": "cursor-2",
            "resultList": {"result": [
                _record("10.1101/a", title="Wet lab microscopy", abstract="No computational work."),
            ]},
        },
        {
            "hitCount": 2,
            "resultList": {"result": [_record("10.1101/b")]},
        },
    ])
    out = BiorxivCollector("biorxiv").collect(
        source=_source(), window=WINDOW, max_results=10, http=http,
    )
    assert out.results_seen == 2
    assert [item.stable_id for item in out.relevant_items] == ["10.1101/b"]
    epmc_calls = [(url, params) for url, params in http.calls if "europepmc" in url]
    assert len(epmc_calls) == 2
    assert epmc_calls[0][1]["cursorMark"] == "*"
    assert epmc_calls[1][1]["cursorMark"] == "cursor-2"


def test_europepmc_fallback_saturates_at_relevant_item_budget():
    http = FallbackHttp([
        {
            "hitCount": 3,
            "resultList": {"result": [
                _record("10.1101/a"),
                _record("10.1101/b"),
                _record("10.1101/c"),
            ]},
        }
    ])
    out = BiorxivCollector("biorxiv").collect(
        source=_source(), window=WINDOW, max_results=2, http=http,
    )
    assert out.execution_status == "partial"
    assert out.saturation_status == "saturated"
    assert len(out.relevant_items) == 2
    assert out.fallback_used is True


def test_europepmc_no_hit_is_partial_not_native_complete():
    http = FallbackHttp([{"hitCount": 0, "resultList": {"result": []}}])
    out = BiorxivCollector("biorxiv").collect(
        source=_source(), window=WINDOW, max_results=10, http=http,
    )
    assert out.execution_status == "partial"
    assert out.saturation_status == "clear"
    assert out.results_seen == 0
    assert out.relevant_items == []
    assert out.fallback_used is True
    assert "coverage_limitation=first_publications_only" in out.diagnostic_note


def test_fallback_failure_still_raises_for_collector_runner_coverage_degradation():
    http = FallbackHttp(fallback_error=TimeoutError("Europe PMC unavailable"))
    with pytest.raises(TimeoutError):
        BiorxivCollector("biorxiv").collect(
            source=_source(), window=WINDOW, max_results=10, http=http,
        )
