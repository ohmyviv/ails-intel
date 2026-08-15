from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.collectors.pubmed import PubMedCollector
from ails_intel.models import SourceSpec


WINDOW = Window(date(2026, 8, 8), date(2026, 8, 15))
SOURCE = SourceSpec(
    "SRC-040",
    "PubMed",
    "P0",
    "site:pubmed.ncbi.nlm.nih.gov (AI OR machine learning) (healthcare OR drug discovery OR biology)",
)


def _article(pmid: str, *, relevant: bool) -> str:
    if relevant:
        title = f"Artificial intelligence drug discovery study {pmid}"
        abstract = "We developed a machine learning model in biology."
    else:
        title = f"Unrelated surgical outcomes {pmid}"
        abstract = "No computational discovery method here."
    return f"""
    <PubmedArticle>
      <MedlineCitation>
        <PMID>{pmid}</PMID>
        <Article>
          <ArticleTitle>{title}</ArticleTitle>
          <Abstract><AbstractText>{abstract}</AbstractText></Abstract>
        </Article>
      </MedlineCitation>
      <PubmedData><History>
        <PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>8</Month><Day>15</Day></PubMedPubDate>
      </History></PubmedData>
    </PubmedArticle>"""


def _page(records) -> str:
    return "<?xml version='1.0'?><PubmedArticleSet>" + "".join(
        _article(pmid, relevant=relevant) for pmid, relevant in records
    ) + "</PubmedArticleSet>"


class HistoryHttp:
    def __init__(self, total: int, pages: dict[int, str]):
        self.total = total
        self.pages = pages
        self.calls = []

    def json(self, url, params=None):
        self.calls.append(("json", url, params))
        return {
            "esearchresult": {
                "count": str(self.total),
                "idlist": [],
                "webenv": "WE-123",
                "querykey": "1",
            }
        }

    def text(self, url, params=None):
        self.calls.append(("text", url, params))
        return self.pages[int(params["retstart"])]


def test_pubmed_history_scans_full_source_set_independent_of_signal_cap():
    sleeps = []
    http = HistoryHttp(
        5,
        {
            0: _page([("1", False), ("2", True)]),
            2: _page([("3", False), ("4", True)]),
            4: _page([("5", False)]),
        },
    )
    out = PubMedCollector(
        scan_budget=10,
        fetch_batch_size=2,
        request_interval_seconds=0.36,
        sleep_fn=sleeps.append,
    ).collect(source=SOURCE, window=WINDOW, max_results=10, http=http)

    assert out.execution_status == "complete"
    assert out.saturation_status == "clear"
    assert out.results_seen == 5
    assert [item.stable_id for item in out.relevant_items] == ["2", "4"]
    assert "source_total=5" in out.diagnostic_note
    assert "scanned=5" in out.diagnostic_note
    assert [call[2]["retstart"] for call in http.calls if call[0] == "text"] == [0, 2, 4]
    assert [call[2]["retmax"] for call in http.calls if call[0] == "text"] == [2, 2, 1]
    assert all(call[2]["WebEnv"] == "WE-123" for call in http.calls if call[0] == "text")
    assert all(call[2]["query_key"] == "1" for call in http.calls if call[0] == "text")
    assert sleeps == [0.36, 0.36, 0.36]
    search_params = http.calls[0][2]
    assert search_params["usehistory"] == "y"
    assert search_params["retmax"] == 0
    assert search_params["datetype"] == "edat"


def test_pubmed_relevant_output_budget_stops_scan_but_remains_truthful_partial():
    http = HistoryHttp(
        5,
        {0: _page([("1", True), ("2", True)])},
    )
    out = PubMedCollector(
        scan_budget=10,
        fetch_batch_size=2,
        request_interval_seconds=0,
    ).collect(source=SOURCE, window=WINDOW, max_results=2, http=http)

    assert out.execution_status == "partial"
    assert out.saturation_status == "saturated"
    assert out.failure_reason == "relevant_budget_exhausted"
    assert out.results_seen == 2
    assert len(out.relevant_items) == 2
    assert len([call for call in http.calls if call[0] == "text"]) == 1


def test_pubmed_scan_budget_is_separate_and_reports_saturation():
    http = HistoryHttp(
        5,
        {
            0: _page([("1", False), ("2", False)]),
            2: _page([("3", False)]),
        },
    )
    out = PubMedCollector(
        scan_budget=3,
        fetch_batch_size=2,
        request_interval_seconds=0,
    ).collect(source=SOURCE, window=WINDOW, max_results=10, http=http)

    assert out.execution_status == "partial"
    assert out.saturation_status == "saturated"
    assert out.failure_reason == "scan_budget_exhausted"
    assert out.results_seen == 3
    assert out.relevant_items == []


def test_pubmed_empty_history_batch_is_partial_unknown_not_complete():
    http = HistoryHttp(3, {0: _page([])})
    out = PubMedCollector(
        scan_budget=10,
        fetch_batch_size=2,
        request_interval_seconds=0,
    ).collect(source=SOURCE, window=WINDOW, max_results=10, http=http)

    assert out.execution_status == "partial"
    assert out.saturation_status == "unknown"
    assert out.failure_reason == "history_fetch_incomplete"
    assert out.results_seen == 0
