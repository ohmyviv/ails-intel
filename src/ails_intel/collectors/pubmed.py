from __future__ import annotations

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import strip_site_prefix

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
                "db": "pubmed", "term": query, "retmode": "json", "retmax": max_results,
                "retstart": 0, "datetype": "edat", "mindate": window.start.isoformat(),
                "maxdate": window.end.isoformat(), "sort": "pub date",
            },
        )
        result = search.get("esearchresult", {})
        ids = list(result.get("idlist") or [])
        total = int(result.get("count") or 0)
        items = []
        if ids:
            summary = http.json(
                f"{self.base}/esummary.fcgi",
                {"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            ).get("result", {})
            for pmid in ids:
                rec = summary.get(str(pmid)) or {}
                title = str(rec.get("title") or "").strip()
                pubdate = str(rec.get("pubdate") or "").strip()
                items.append(RawItem(
                    stable_id=str(pmid), title=title,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    published_date=pubdate, event_date=pubdate, first_public_at=pubdate,
                    snippet=str(rec.get("fulljournalname") or rec.get("source") or "").strip(),
                ))
        saturated = total > max_results
        return CollectorOutcome(
            collector_id=self.collector_id, source_id=self.source_id, channel_id=self.channel_id,
            execution_status="partial" if saturated else "complete",
            saturation_status="saturated" if saturated else "clear",
            results_seen=len(ids), relevant_items=items,
            representative_url=items[0].url if items else "",
        )
