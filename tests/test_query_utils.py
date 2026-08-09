from ails_intel.query_utils import (
    arxiv_search_expression,
    ctgov_search_expression,
    extract_private_terms,
    local_relevance,
    query_groups,
    strip_site_prefix,
)


def test_strip_site():
    assert strip_site_prefix('site:example.org ("virtual cell" OR AI)') == '("virtual cell" OR AI)'


def test_extract_private_terms():
    assert extract_private_terms('site:example.org ("virtual cell" OR AI)') == ["virtual cell", "AI"]


def test_query_groups_preserve_and_between_parentheses():
    q = 'site:x (AI OR machine learning) (healthcare OR drug discovery OR biology)'
    assert query_groups(q) == [["AI", "machine learning"], ["healthcare", "drug discovery", "biology"]]


def test_local_relevance_single_or_group_accepts_any_alternative():
    q = 'site:x ("virtual cell" OR AI OR clinical)'
    assert local_relevance("A virtual cell model", q)
    assert local_relevance("Clinical outcomes only", q)
    assert not local_relevance("Protein assay only", q)


def test_local_relevance_requires_each_group():
    q = 'site:x (AI OR machine learning) (healthcare OR drug discovery OR biology)'
    assert local_relevance("AI for drug discovery", q)
    assert local_relevance("Machine-learning methods in biology", q)
    assert not local_relevance("AI for industrial robotics", q)
    assert not local_relevance("Biology assay without computational methods", q)


def test_arxiv_query_preserves_groups_and_date():
    q = arxiv_search_expression(
        'site:x (AI OR "machine learning") ("drug discovery" OR biology)',
        "202608010000",
        "202608092359",
    )
    assert '(all:AI OR all:"machine learning")' in q
    assert '(all:"drug discovery" OR all:biology)' in q
    assert " AND " in q
    assert "submittedDate:[202608010000 TO 202608092359]" in q


def test_ctgov_query_has_range():
    q = ctgov_search_expression(
        'site:clinicaltrials.gov ("artificial intelligence" OR "machine learning")',
        "2026-08-01",
        "2026-08-09",
    )
    assert "AREA[LastUpdatePostDate]RANGE[2026-08-01, 2026-08-09]" in q
    assert "site:" not in q
