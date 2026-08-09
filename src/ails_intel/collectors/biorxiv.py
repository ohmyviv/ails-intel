from __future__ import annotations

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import local_relevance

class BiorxivCollector:
    channel_id = "C5"
    base = "https://api.biorxiv.org/details"

    def __init__(self, server: str):
        if server not in {"biorxiv", "medrxiv"}:
            raise ValueError("server must be biorxiv or medrxiv")
        self.server = server
        self.collector_id = "COL-BIORXIV" if server == "biorxiv" else "COL-MEDRXIV"
        self.source_id = "SRC-019" if server == "biorxiv" else "SRC-020"

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        cursor = 0
        seen = 0
        relevant: list[RawItem] = []
        saturated = False
        interval = f"{window.start.isoformat()}/{window.end.isoformat()}"
        while True:
            payload = http.json(f"{self.base}/{self.server}/{interval}/{cursor}")
            collection = payload.get("collection") or []
            seen += len(collection)
            for rec in collection:
                title = str(rec.get("title") or "").strip()
                abstract = str(rec.get("abstract") or "").strip()
                if local_relevance(f"{title}\n{abstract}", source.query_template):
                    doi = str(rec.get("doi") or "").strip()
                    pubdate = str(rec.get("date") or "").strip()
                    relevant.append(RawItem(
                        stable_id=doi, title=title,
                        url=f"https://www.{self.server}.org/content/{doi}" if doi else "",
                        published_date=pubdate, event_date=pubdate, first_public_at=pubdate,
                        snippet=abstract[:1200],
                    ))
                    if len(relevant) >= max_results:
                        saturated = True
            messages = payload.get("messages") or []
            total = None
            if messages:
                msg = messages[0]
                for key in ("total", "count"):
                    try:
                        total = int(msg.get(key))
                        break
                    except (TypeError, ValueError):
                        pass
            cursor += len(collection)
            if not collection or (total is not None and cursor >= total):
                break
            if saturated:
                break
        relevant = relevant[:max_results]
        return CollectorOutcome(
            collector_id=self.collector_id, source_id=self.source_id, channel_id=self.channel_id,
            execution_status="partial" if saturated else "complete",
            saturation_status="saturated" if saturated else "clear",
            results_seen=seen, relevant_items=relevant,
            representative_url=relevant[0].url if relevant else "",
        )
