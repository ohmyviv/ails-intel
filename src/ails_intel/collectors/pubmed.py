from __future__ import annotations

import calendar
import xml.etree.ElementTree as ET
from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import local_relevance, strip_site_prefix


PUBLIC_STATUSES = {"aheadofprint", "epublish", "ecollection", "ppublish"}
ENTRY_STATUSES = ("pubmed", "entrez")
MONTHS = {name.casefold(): idx for idx, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.casefold(): idx for idx, name in enumerate(calendar.month_abbr) if name})


def _node_text(node) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _history_date(node) -> date | None:
    try:
        year = int(node.findtext("Year") or "")
        raw_month = (node.findtext("Month") or "1").strip()
        try:
            month = int(raw_month)
        except ValueError:
            month = MONTHS.get(raw_month.casefold(), 1)
        day = int((node.findtext("Day") or "1").strip())
        return date(year, month, day)
    except (TypeError, ValueError):
        return None


def _first_public_date(article, window_end: date) -> str:
    history = article.find("./PubmedData/History")
    by_status: dict[str, list[date]] = {}
    if history is not None:
        for node in history.findall("PubMedPubDate"):
            status = (node.attrib.get("PubStatus") or "").casefold()
            parsed = _history_date(node)
            if parsed is not None:
                by_status.setdefault(status, []).append(parsed)

    public_dates = [
        d
        for status in PUBLIC_STATUSES
        for d in by_status.get(status, [])
        if d <= window_end
    ]
    if public_dates:
        return min(public_dates).isoformat()

    # If the publisher-public history is absent, PubMed/Entrez entry dates are a
    # safer discovery timestamp than a future issue date from Journal/PubDate.
    for status in ENTRY_STATUSES:
        dates = [d for d in by_status.get(status, []) if d <= window_end]
        if dates:
            return min(dates).isoformat()
    return ""


class PubMedCollector:
    collector_id = "COL-PUBMED"
    source_id = "SRC-040"
    channel_id = "C5"
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        query = strip_site_prefix(source.query_template)
        search = http.json(
            f"{self.base}/esearch.fcgi",
            {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": max_results,
                "retstart": 0,
                # EDAT is intentionally used for discovery: the run is asking
                # what PubMed learned about in the bounded interval, not merely
                # which journal issue carries that calendar date.
                "datetype": "edat",
                "mindate": window.start.strftime("%Y/%m/%d"),
                "maxdate": window.end.strftime("%Y/%m/%d"),
                "sort": "pub_date",
            },
        )
        result = search.get("esearchresult", {})
        ids = list(result.get("idlist") or [])
        total = int(result.get("count") or 0)
        items: list[RawItem] = []

        if ids:
            xml = http.text(
                f"{self.base}/efetch.fcgi",
                {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            )
            root = ET.fromstring(xml)
            for article in root.findall("PubmedArticle"):
                pmid = (article.findtext("./MedlineCitation/PMID") or "").strip()
                title = _node_text(article.find("./MedlineCitation/Article/ArticleTitle"))
                abstract_parts = []
                for node in article.findall("./MedlineCitation/Article/Abstract/AbstractText"):
                    label = (node.attrib.get("Label") or "").strip()
                    text = _node_text(node)
                    if text:
                        abstract_parts.append(f"{label}: {text}" if label else text)
                abstract = " ".join(abstract_parts).strip()
                if not local_relevance(f"{title}\n{abstract}", source.query_template):
                    continue

                first_public = _first_public_date(article, window.end)
                if not first_public:
                    # The ESearch EDAT window proves the record is newly visible
                    # in this interval even when a detailed public-date history
                    # is absent. Use the bounded discovery end as conservative
                    # fallback rather than a potentially future issue date.
                    first_public = window.end.isoformat()
                items.append(
                    RawItem(
                        stable_id=pmid,
                        title=title,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                        published_date=first_public,
                        event_date=first_public,
                        first_public_at=first_public,
                        snippet=abstract[:1200],
                    )
                )

        saturated = total > max_results
        return CollectorOutcome(
            collector_id=self.collector_id,
            source_id=self.source_id,
            channel_id=self.channel_id,
            execution_status="partial" if saturated else "complete",
            saturation_status="saturated" if saturated else "clear",
            results_seen=len(ids),
            relevant_items=items,
            representative_url=items[0].url if items else "",
        )
