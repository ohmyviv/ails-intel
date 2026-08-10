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


def test_pubmed_precision_gate_filters_reviews_and_nonoriginal_records():
    xml = """<?xml version="1.0"?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation><PMID>10</PMID><Article>
          <ArticleTitle>Artificial intelligence in drug discovery review</ArticleTitle>
          <Abstract><AbstractText>This review summarizes machine learning in biology.</AbstractText></Abstract>
          <PublicationTypeList><PublicationType>Review</PublicationType></PublicationTypeList>
        </Article></MedlineCitation>
        <PubmedData><History><PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>8</Month><Day>8</Day></PubMedPubDate></History></PubmedData>
      </PubmedArticle>
      <PubmedArticle>
        <MedlineCitation><PMID>11</PMID><Article>
          <ArticleTitle>Artificial intelligence model for drug discovery</ArticleTitle>
          <Abstract>
            <AbstractText Label="METHODS">We developed a machine learning model in biology.</AbstractText>
            <AbstractText Label="RESULTS">The model improved prospective screening.</AbstractText>
          </Abstract>
          <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
        </Article></MedlineCitation>
        <PubmedData><History><PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>8</Month><Day>8</Day></PubMedPubDate></History></PubmedData>
      </PubmedArticle>
      <PubmedArticle>
        <MedlineCitation><PMID>12</PMID><Article>
          <ArticleTitle>Artificial intelligence and biology perspective</ArticleTitle>
          <Abstract><AbstractText>Machine learning may transform future drug discovery.</AbstractText></Abstract>
          <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
        </Article></MedlineCitation>
        <PubmedData><History><PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>8</Month><Day>8</Day></PubMedPubDate></History></PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>"""
    http = FakeHttp(
        [{"esearchresult": {"count": "3", "idlist": ["10", "11", "12"]}}],
        text_response=xml,
    )
    source = SourceSpec(
        "SRC-040", "PubMed", "P0",
        "site:pubmed.ncbi.nlm.nih.gov (AI OR machine learning) (drug discovery OR biology)",
    )
    gate = {
        "enabled": True,
        "exclude_publication_types": ["Review", "Systematic Review", "Meta-Analysis"],
        "require_original_contribution": True,
        "strong_original_publication_types": ["Clinical Trial", "Randomized Controlled Trial", "Evaluation Study", "Validation Study"],
        "original_markers": ["we present", "we develop", "we developed", "we evaluate", "we evaluated", "we validate", "we introduce"],
        "original_abstract_labels": ["methods", "results"],
    }
    out = PubMedCollector(gate_options=gate).collect(source=source, window=W, max_results=10, http=http)
    assert [x.stable_id for x in out.relevant_items] == ["11"]
    assert "filtered_pubtype=1" in out.diagnostic_note
    assert "filtered_nonoriginal=1" in out.diagnostic_note


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


def _ctgov_core_payload(last_update="2026-08-08"):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCTX", "briefTitle": "Artificial intelligence diagnostic validation"},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdatePostDateStruct": {"date": last_update},
                "studyFirstPostDateStruct": {"date": "2026-08-05"},
                "startDateStruct": {"date": "2026-08-01"},
            },
            "descriptionModule": {"briefSummary": "Prospective clinical validation of an AI diagnostic system."},
            "armsInterventionsModule": {
                "interventions": [{"type": "DEVICE", "name": "AI diagnostic software", "description": "Machine learning decision support"}]
            },
            "outcomesModule": {
                "primaryOutcomes": [{"measure": "AI diagnostic sensitivity", "timeFrame": "Day 1"}]
            },
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "phases": ["NA"],
                "enrollmentInfo": {"count": 120},
                "designInfo": {"allocation": "RANDOMIZED", "interventionModel": "PARALLEL"},
            },
        },
        "hasResults": False,
    }


def _ctgov_gate():
    return {
        "enabled": True,
        "ai_terms": ["artificial intelligence", "AI", "machine learning", "large language model"],
        "role_terms": ["clinical validation", "diagnostic", "predict", "decision support", "randomized", "prospective"],
        "low_value_terms": ["education", "survey", "attitude"],
        "weights": {"title": 3, "intervention": 4, "outcome": 3, "summary": 1, "role": 2, "low_value_penalty": 2},
        "core_threshold": 5,
        "p1_threshold": 8,
        "material_delta_enabled": True,
        "p1_deltas": ["new_registration", "status_changed", "results_posted"],
    }


def test_ctgov_ai_role_gate_assigns_priority_and_material_metadata():
    low = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCTLOW", "briefTitle": "AI education survey"},
            "statusModule": {
                "lastUpdatePostDateStruct": {"date": "2026-08-08"},
                "studyFirstPostDateStruct": {"date": "2026-08-08"},
            },
            "descriptionModule": {"briefSummary": "Survey of attitudes toward AI education."},
        }
    }
    http = FakeHttp([{"studies": [_ctgov_core_payload(), low]}])
    source = SourceSpec("SRC-021", "CTG", "P0", '("artificial intelligence" OR AI OR "machine learning")')
    out = ClinicalTrialsCollector(gate_options=_ctgov_gate()).collect(source=source, window=W, max_results=10, http=http)
    assert [x.stable_id for x in out.relevant_items] == ["NCTX"]
    assert out.relevant_items[0].priority_hint == "P1"
    assert "ctgov_material=" in out.relevant_items[0].notes
    assert "ctgov_delta=new_registration" in out.relevant_items[0].notes
    assert "filtered_noncore=1" in out.diagnostic_note


def test_ctgov_material_gate_suppresses_unchanged_registry_refresh():
    source = SourceSpec("SRC-021", "CTG", "P0", '("artificial intelligence" OR AI OR "machine learning")')
    first = ClinicalTrialsCollector(gate_options=_ctgov_gate()).collect(
        source=source,
        window=W,
        max_results=10,
        http=FakeHttp([{"studies": [_ctgov_core_payload("2026-08-08")]}]),
    )
    item = first.relevant_items[0]
    prior = {
        "NCTX": {
            "raw_title": item.title,
            "raw_snippet": item.snippet,
            "notes": item.notes,
        }
    }
    second = ClinicalTrialsCollector(gate_options=_ctgov_gate(), prior_signals=prior).collect(
        source=source,
        window=W,
        max_results=10,
        http=FakeHttp([{"studies": [_ctgov_core_payload("2026-08-09")]}]),
    )
    assert second.relevant_items == []
    assert "filtered_unchanged=1" in second.diagnostic_note
