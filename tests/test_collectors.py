from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.collectors.pubmed import PubMedCollector
from ails_intel.collectors.arxiv import ArxivCollector
from ails_intel.collectors.biorxiv import BiorxivCollector
from ails_intel.collectors.clinicaltrials import ClinicalTrialsCollector
from ails_intel.models import SourceSpec

class FakeHttp:
    def __init__(self, json_responses=None, text_response=""):
        self.json_responses=list(json_responses or [])
        self.text_response=text_response
        self.calls=[]
    def json(self, url, params=None):
        self.calls.append((url,params))
        return self.json_responses.pop(0)
    def text(self, url, params=None):
        self.calls.append((url,params))
        return self.text_response

W=Window(date(2026,8,1),date(2026,8,9))

def test_pubmed_marks_saturated():
    http=FakeHttp([
        {"esearchresult":{"count":"2","idlist":["1"]}},
        {"result":{"1":{"title":"AI biology","pubdate":"2026 Aug 8","fulljournalname":"J"}}},
    ])
    source=SourceSpec("SRC-040","PubMed","P0",'site:pubmed.ncbi.nlm.nih.gov ("AI" OR "biology")')
    out=PubMedCollector().collect(source=source,window=W,max_results=1,http=http)
    assert out.execution_status=="partial"
    assert out.saturation_status=="saturated"
    assert out.relevant_items[0].stable_id=="1"

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
    http=FakeHttp(text_response=xml)
    source=SourceSpec("SRC-018","arXiv","P1",'site:arxiv.org ("virtual cell")')
    out=ArxivCollector().collect(source=source,window=W,max_results=10,http=http)
    assert out.execution_status=="complete"
    assert out.relevant_items[0].stable_id=="2608.00001v1"

def test_biorxiv_local_filter():
    http=FakeHttp([{
        "messages":[{"total":"2"}],
        "collection":[
            {"doi":"10.1/a","title":"Virtual cell foundation","abstract":"x","date":"2026-08-08"},
            {"doi":"10.1/b","title":"Wet lab only","abstract":"unrelated","date":"2026-08-08"},
        ],
    }])
    source=SourceSpec("SRC-019","bioRxiv","P1",'site:biorxiv.org ("virtual cell" OR AI OR biology)')
    out=BiorxivCollector("biorxiv").collect(source=source,window=W,max_results=10,http=http)
    assert out.results_seen==2
    assert [x.stable_id for x in out.relevant_items]==["10.1/a"]

def test_ctgov_parses_study():
    http=FakeHttp([{
        "totalCount":1,
        "studies":[{
            "protocolSection":{
                "identificationModule":{"nctId":"NCT1","briefTitle":"AI trial"},
                "statusModule":{"lastUpdatePostDateStruct":{"date":"2026-08-08"},"studyFirstPostDateStruct":{"date":"2026-07-01"}},
                "descriptionModule":{"briefSummary":"summary"},
            }
        }]
    }])
    source=SourceSpec("SRC-021","CTG","P0",'site:clinicaltrials.gov ("artificial intelligence")')
    out=ClinicalTrialsCollector().collect(source=source,window=W,max_results=10,http=http)
    assert out.execution_status=="complete"
    assert out.relevant_items[0].stable_id=="NCT1"
