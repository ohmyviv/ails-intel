from datetime import date

from ails_intel.collectors.arxiv import ArxivCollector
from ails_intel.collectors.base import Window
from ails_intel.collectors.biorxiv import BiorxivCollector
from ails_intel.collectors.clinicaltrials import ClinicalTrialsCollector
from ails_intel.collectors.pubmed import PubMedCollector
from ails_intel.models import SourceSpec


class FakeHttp:
    def __init__(self, json_responses=None, text_response=""):
        self.json_responses = list(json_responses or [])
        self.text_response = text_response
        self.calls = []

    def json(self, url, params=None):
        self.calls.append((url, params))
        return self.json_responses.pop(0)

    def text(self, url, params=None):
        self.calls.append((url, params))
        return self.text_response


W = Window(date(2026, 8, 1), date(2026, 8, 9))


def _pubmed_xml() -> str:
    return """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>1</PMID>
          <Article>
            <Journal><JournalIssue><PubDate><Year>2027</Year><Month>Feb</Month></PubDate></JournalIssue></Journal>
            <ArticleTitle>Artificial intelligence for drug discovery</ArticleTitle>
            <Abstract><AbstractText>Machine learning methods in biology.</AbstractText></Abstract>
          </Article>
        </MedlineCitation>
        <PubmedData><History>
          <PubMedPubDate PubStatus="aheadofprint"><Year>2026</Year><Month>8</Month><Day>8</Day></PubMedPubDate>
          <PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>8</Month><Day>9</Day></PubMedPubDate>
          <PubMedPubDate PubStatus="ppublish"><Year>2027</Year><Month>2</Month><Day>1</Day></PubMedPubDate>
        </History></PubmedData>
      </PubmedArticle>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>2</PMID>
          <Article>
            <ArticleTitle>Unrelated surgical outcomes</ArticleTitle>
            <Abstract><AbstractText>No computational discovery method here.</AbstractText></Abstract>
          </Article>
        </MedlineCitation>
        <PubmedData><History>
          <PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>8</Month><Day>9</Day></PubMedPubDate>
        </History></PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>"""


def test_pubmed_marks_saturated_filters_locally_and_uses_first_public_date():
    http = FakeHttp(
        [{"esearchresult": {"count": "3", "idlist": ["1", "2"]}}],
        text_response=_pubmed_xml(),
    )
    source = SourceSpec(
        "SRC-040",
        "PubMed",
        "P0",
        "site:pubmed.ncbi.nlm.nih.gov (AI OR machine learning) (healthcare OR drug discovery OR biology)",
    )
    out = PubMedCollector().collect(source=source, window=W, max_results=2, http=http)
    assert out.execution_status == "partial"
    assert out.saturation_status == "saturated"
    assert out.results_seen == 2
    assert [x.stable_id for x in out.relevant_items] == ["1"]
    assert out.relevant_items[0].published_date == "2026-08-08"
    assert out.relevant_items[0].first_public_at == "2026-08-08"
    assert http.calls[0][1]["datetype"] == "edat"
    assert http.calls[0][1]["sort"] == "pub_date"


def test_arxiv_parses_atom():
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
      <opensearch:totalResults>1</opensearch:totalResults>
      <entry>
        <id>https://arxiv.org/abs/2608.00001v1</id>
        <title> Virtual Cell </title>
        <summary>Test abstract</summary>
        <published>2026-08-08T01:02:03Z</published>
      </entry>
    </feed>"""
    http = FakeHttp(text_response=xml)
    source = SourceSpec("SRC-018", "arXiv", "P1", 'site:arxiv.org ("virtual cell")')
    out = ArxivCollector().collect(source=source, window=W, max_results=10, http=http)
    assert out.execution_status == "complete"
    assert out.relevant_items[0].stable_id == "2608.00001v1"


def test_biorxiv_local_filter():
    http = FakeHttp(
        [{
            "messages": [{"total": "2"}],
            "collection": [
                {"doi": "10.1/a", "title": "Virtual cell foundation", "abstract": "x", "date": "2026-08-08"},
                {"doi": "10.1/b", "title": "Wet lab only", "abstract": "unrelated", "date": "2026-08-08"},
            ],
        }]
    )
    source = SourceSpec("SRC-019", "bioRxiv", "P1", 'site:biorxiv.org ("virtual cell" OR AI OR "protein design")')
    out = BiorxivCollector("biorxiv").collect(source=source, window=W, max_results=10, http=http)
    assert out.results_seen == 2
    assert [x.stable_id for x in out.relevant_items] == ["10.1/a"]


def test_ctgov_filters_nonmatching_registry_records():
    http = FakeHttp(
        [{
            "totalCount": 2,
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": "NCT1", "briefTitle": "Artificial intelligence trial"},
                        "statusModule": {
                            "lastUpdatePostDateStruct": {"date": "2026-08-08"},
                            "studyFirstPostDateStruct": {"date": "2026-07-01"},
                        },
                        "descriptionModule": {"briefSummary": "AI-supported clinical workflow."},
                    }
                },
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": "NCT2", "briefTitle": "Standard chemotherapy study"},
                        "statusModule": {
                            "lastUpdatePostDateStruct": {"date": "2026-08-08"},
                            "studyFirstPostDateStruct": {"date": "2026-07-01"},
                        },
                        "descriptionModule": {"briefSummary": "Drug efficacy study without computational methods."},
                    }
                },
            ],
        }]
    )
    source = SourceSpec(
        "SRC-021",
        "CTG",
        "P0",
        'site:clinicaltrials.gov ("artificial intelligence" OR "AI-designed" OR "machine learning")',
    )
    out = ClinicalTrialsCollector().collect(source=source, window=W, max_results=10, http=http)
    assert out.execution_status == "complete"
    assert out.results_seen == 2
    assert [x.stable_id for x in out.relevant_items] == ["NCT1"]
