from ails_intel.query_utils import arxiv_search_expression, ctgov_search_expression, extract_private_terms, local_relevance, strip_site_prefix

def test_strip_site():
    assert strip_site_prefix('site:example.org ("virtual cell" OR AI)') == '("virtual cell" OR AI)'

def test_extract_private_terms():
    assert extract_private_terms('site:example.org ("virtual cell" OR AI)') == ["virtual cell", "AI"]

def test_local_relevance_phrase_or_two_singles():
    q='site:x ("virtual cell" OR AI OR clinical)'
    assert local_relevance("A virtual cell model", q)
    assert local_relevance("Clinical AI validation", q)
    assert not local_relevance("Clinical outcomes only", q)

def test_arxiv_query_has_date_and_terms():
    q=arxiv_search_expression('site:x ("virtual cell" OR "drug discovery")',"202608010000","202608092359")
    assert 'all:"virtual cell"' in q
    assert "submittedDate:[202608010000 TO 202608092359]" in q

def test_ctgov_query_has_range():
    q=ctgov_search_expression('site:clinicaltrials.gov ("artificial intelligence" OR "machine learning")',"2026-08-01","2026-08-09")
    assert "AREA[LastUpdatePostDate]RANGE[2026-08-01, 2026-08-09]" in q
    assert "site:" not in q
