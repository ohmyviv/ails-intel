from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.collectors.biorxiv import BiorxivCollector
from ails_intel.models import SourceSpec


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def json(self, url, params=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def source(server="medRxiv"):
    return SourceSpec(
        "SRC-020" if server == "medRxiv" else "SRC-019",
        server,
        "P1",
        f"site:{server.lower()}.org (AI OR model)",
    )


def test_revised_preprint_keeps_revision_date_but_recovers_v1_first_public():
    interval = {
        "messages": [{"total": "1"}],
        "collection": [{
            "doi": "10.64898/2026.06.24.26356357",
            "version": "2",
            "date": "2026-08-07",
            "title": "AI model for clinical screening",
            "abstract": "AI model in healthcare",
        }],
    }
    history = {
        "collection": [
            {"doi": "10.64898/2026.06.24.26356357", "version": "1", "date": "2026-07-01"},
            {"doi": "10.64898/2026.06.24.26356357", "version": "2", "date": "2026-08-07"},
        ]
    }
    http = FakeHttp([interval, history])
    out = BiorxivCollector("medrxiv").collect(
        source=source(),
        window=Window(date(2026, 8, 1), date(2026, 8, 9)),
        max_results=10,
        http=http,
    )
    item = out.relevant_items[0]
    assert item.event_date == "2026-08-07"
    assert item.published_date == "2026-08-07"
    assert item.first_public_at == "2026-07-01"
    assert len(http.calls) == 2
    assert http.calls[1][0].endswith("/medrxiv/10.64898/2026.06.24.26356357/na")


def test_v1_preprint_does_not_require_history_lookup():
    http = FakeHttp([{
        "messages": [{"total": "1"}],
        "collection": [{
            "doi": "10.64898/2026.08.05.743095",
            "version": "1",
            "date": "2026-08-06",
            "title": "AI model for mass spectra",
            "abstract": "AI model for molecules",
        }],
    }])
    out = BiorxivCollector("biorxiv").collect(
        source=source("bioRxiv"),
        window=Window(date(2026, 8, 1), date(2026, 8, 9)),
        max_results=10,
        http=http,
    )
    item = out.relevant_items[0]
    assert item.first_public_at == "2026-08-06"
    assert len(http.calls) == 1


def test_history_enrichment_failure_does_not_fail_collector():
    class FailingHistoryHttp(FakeHttp):
        def json(self, url, params=None):
            self.calls.append((url, params))
            if len(self.calls) == 1:
                return self.responses.pop(0)
            raise TimeoutError("history unavailable")

    http = FailingHistoryHttp([{
        "messages": [{"total": "1"}],
        "collection": [{
            "doi": "10.1/revised",
            "version": "2",
            "date": "2026-08-08",
            "title": "AI revised model",
            "abstract": "AI model in biology",
        }],
    }])
    out = BiorxivCollector("biorxiv").collect(
        source=source("bioRxiv"),
        window=Window(date(2026, 8, 1), date(2026, 8, 9)),
        max_results=10,
        http=http,
    )
    assert out.execution_status == "complete"
    assert out.relevant_items[0].first_public_at == "2026-08-08"
