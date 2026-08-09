from __future__ import annotations

import re

SITE_PREFIX = re.compile(r"\bsite:\S+\s*", re.I)
GROUP = re.compile(r"\(([^()]*)\)")
OR_SPLIT = re.compile(r"\s+OR\s+", re.I)
QUOTED = re.compile(r'^["\'](.*)["\']$')
TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9-]{1,}\b")
STOP = {"or","and","not","site","www","org","com","gov","arxiv","biorxiv","medrxiv","pubmed","ncbi","clinicaltrials"}
NONWORD = re.compile(r"[^a-z0-9]+", re.I)
WS = re.compile(r"\s+")


def strip_site_prefix(query: str) -> str:
    return SITE_PREFIX.sub("", query or "").strip()


def _clean_alt(value: str) -> str:
    value = value.strip()
    m = QUOTED.match(value)
    if m:
        value = m.group(1).strip()
    return value


def query_groups(query: str) -> list[list[str]]:
    """Return parenthesized OR groups while preserving AND-between-groups semantics.

    Private operational queries use a deliberately small grammar such as:
      (AI OR machine learning) (healthcare OR drug discovery OR biology)
    Adjacent parenthesized groups are interpreted as AND, and alternatives inside
    each group are interpreted as OR. The exact vocabulary remains runtime data.
    """
    q = strip_site_prefix(query)
    groups: list[list[str]] = []
    for raw_group in GROUP.findall(q):
        alternatives = [_clean_alt(x) for x in OR_SPLIT.split(raw_group)]
        alternatives = [x for x in alternatives if x]
        if alternatives:
            groups.append(alternatives)
    if groups:
        return groups

    # Fallback for a simple non-parenthesized query. Treat explicit OR terms as
    # one group. If no OR is present, the whole expression is one phrase.
    alternatives = [_clean_alt(x) for x in OR_SPLIT.split(q)]
    alternatives = [x for x in alternatives if x]
    return [alternatives] if alternatives else []


def extract_private_terms(query: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    groups = query_groups(query)
    values = [term for group in groups for term in group]
    if not values:
        q = strip_site_prefix(query)
        values = [tok for tok in TOKEN.findall(q) if tok.casefold() not in STOP]
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _normalized(value: str) -> str:
    return WS.sub(" ", NONWORD.sub(" ", (value or "").casefold())).strip()


def _term_matches(text_normalized: str, term: str) -> bool:
    needle = _normalized(term)
    if not needle:
        return False
    if " " in needle:
        return needle in text_normalized
    return re.search(rf"\b{re.escape(needle)}\b", text_normalized) is not None


def local_relevance(text: str, query: str) -> bool:
    """Evaluate the private query's small AND-of-OR-groups grammar locally."""
    groups = query_groups(query)
    if not groups:
        return True
    hay = _normalized(text)
    return all(any(_term_matches(hay, term) for term in group) for group in groups)


def _arxiv_atom(term: str) -> str:
    cleaned = term.replace('"', "").strip()
    return f'all:"{cleaned}"' if " " in cleaned else f"all:{cleaned}"


def arxiv_search_expression(query: str, start_utc: str, end_utc: str) -> str:
    groups = query_groups(query)
    if not groups:
        content = "all:*"
    else:
        rendered = ["(" + " OR ".join(_arxiv_atom(term) for term in group) + ")" for group in groups]
        content = " AND ".join(rendered)
    return f"{content} AND submittedDate:[{start_utc} TO {end_utc}]"


def ctgov_search_expression(query: str, start_date: str, end_date: str) -> str:
    content = strip_site_prefix(query) or "ALL"
    return f"({content}) AND AREA[LastUpdatePostDate]RANGE[{start_date}, {end_date}]"
