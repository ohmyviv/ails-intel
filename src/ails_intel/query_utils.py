from __future__ import annotations

import re

SITE_PREFIX = re.compile(r"\bsite:\S+\s*", re.I)
QUOTED = re.compile(r'"([^"]+)"')
TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9-]{1,}\b")
STOP = {"or","and","not","site","www","org","com","gov","arxiv","biorxiv","medrxiv","pubmed","ncbi","clinicaltrials"}

def strip_site_prefix(query: str) -> str:
    return SITE_PREFIX.sub("", query or "").strip()

def extract_private_terms(query: str) -> list[str]:
    q = strip_site_prefix(query)
    phrases = [x.strip() for x in QUOTED.findall(q) if x.strip()]
    remainder = QUOTED.sub(" ", q)
    singles = []
    for tok in TOKEN.findall(remainder):
        t = tok.strip()
        if t.lower() in STOP:
            continue
        if t not in singles and t not in phrases:
            singles.append(t)
    seen = set()
    out = []
    for term in phrases + singles:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out

def local_relevance(text: str, query: str) -> bool:
    hay = " ".join((text or "").casefold().split())
    terms = extract_private_terms(query)
    if not terms:
        return True
    multi = [t for t in terms if " " in t]
    if any(t.casefold() in hay for t in multi):
        return True
    single = [t for t in terms if " " not in t]
    matched = sum(1 for t in single if re.search(rf"\b{re.escape(t.casefold())}\b", hay))
    needed = 1 if len(single) <= 1 else 2
    return matched >= needed

def arxiv_search_expression(query: str, start_utc: str, end_utc: str) -> str:
    terms = extract_private_terms(query)
    if not terms:
        content = "all:*"
    else:
        atoms = []
        for term in terms:
            escaped = term.replace('"', "")
            atoms.append(f'all:"{escaped}"' if " " in escaped else f"all:{escaped}")
        content = "(" + " OR ".join(atoms) + ")"
    return f"{content} AND submittedDate:[{start_utc} TO {end_utc}]"

def ctgov_search_expression(query: str, start_date: str, end_date: str) -> str:
    content = strip_site_prefix(query) or "ALL"
    return f"({content}) AND AREA[LastUpdatePostDate]RANGE[{start_date}, {end_date}]"
