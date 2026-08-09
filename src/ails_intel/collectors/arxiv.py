from __future__ import annotations

import xml.etree.ElementTree as ET

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import arxiv_search_expression

ATOM = "http://www.w3.org/2005/Atom"
OPEN = "http://a9.com/-/spec/opensearch/1.1/"

class ArxivCollector:
    collector_id = "COL-ARXIV"
    source_id = "SRC-018"
    channel_id = "C5"
    base = "https://export.arxiv.org/api/query"

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        start_utc = window.start.strftime("%Y%m%d") + "0000"
        end_utc = window.end.strftime("%Y%m%d") + "2359"
        query = arxiv_search_expression(source.query_template, start_utc, end_utc)
        xml = http.text(self.base, {
            "search_query": query, "start": 0, "max_results": max_results,
            "sortBy": "submittedDate", "sortOrder": "descending",
        })
        root = ET.fromstring(xml)
        total_text = root.findtext(f"{{{OPEN}}}totalResults") or "0"
        try:
            total = int(total_text)
        except ValueError:
            total = 0
        items = []
        for entry in root.findall(f"{{{ATOM}}}entry"):
            ident = (entry.findtext(f"{{{ATOM}}}id") or "").strip()
            stable = ident.rstrip("/").split("/")[-1]
            title = " ".join((entry.findtext(f"{{{ATOM}}}title") or "").split())
            summary = " ".join((entry.findtext(f"{{{ATOM}}}summary") or "").split())
            published = (entry.findtext(f"{{{ATOM}}}published") or "").strip()
            pubdate = published[:10]
            items.append(RawItem(
                stable_id=stable, title=title, url=ident, published_date=pubdate,
                event_date=pubdate, first_public_at=published or pubdate, snippet=summary[:1200],
            ))
        saturated = total > max_results
        return CollectorOutcome(
            collector_id=self.collector_id, source_id=self.source_id, channel_id=self.channel_id,
            execution_status="partial" if saturated else "complete",
            saturation_status="saturated" if saturated else "clear",
            results_seen=len(items), relevant_items=items,
            representative_url=items[0].url if items else "",
        )
