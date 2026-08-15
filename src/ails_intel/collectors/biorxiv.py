from __future__ import annotations

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import local_relevance


class BiorxivCollector:
    channel_id = "C5"
    base = "https://api.biorxiv.org/details"
    europe_pmc_base = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    europe_pmc_page_size = 1000

    def __init__(self, server: str):
        if server not in {"biorxiv", "medrxiv"}:
            raise ValueError("server must be biorxiv or medrxiv")
        self.server = server
        self.collector_id = "COL-BIORXIV" if server == "biorxiv" else "COL-MEDRXIV"
        self.source_id = "SRC-019" if server == "biorxiv" else "SRC-020"

    @property
    def europe_pmc_publisher(self) -> str:
        return "bioRxiv" if self.server == "biorxiv" else "medRxiv"

    @staticmethod
    def _version(rec: dict) -> int:
        try:
            return int(str(rec.get("version") or "1"))
        except (TypeError, ValueError):
            return 1

    def _first_public_date(self, rec: dict, *, http, cache: dict[str, str]) -> str:
        """Resolve v1 date without losing the current revision date.

        openRxiv's interval API includes both new and revised manuscripts, and
        the record ``date`` is the date of that returned version. For v2+ this
        is therefore a material-update date, not the manuscript's first-public
        date. The DOI-detail endpoint returns the manuscript's version history,
        so revised relevant records get one cached DOI lookup to recover v1.

        A history lookup is enrichment rather than a reason to fail an entire
        source scan: if it is temporarily unavailable, retain the current-version
        date and let downstream verification treat first-public timing cautiously.
        """
        pubdate = str(rec.get("date") or "").strip()
        doi = str(rec.get("doi") or "").strip()
        if not doi or self._version(rec) <= 1:
            return pubdate
        if doi in cache:
            return cache[doi]

        first = pubdate
        try:
            payload = http.json(f"{self.base}/{self.server}/{doi}/na")
            dates = sorted(
                str(item.get("date") or "").strip()
                for item in (payload.get("collection") or [])
                if str(item.get("date") or "").strip()
            )
            if dates:
                first = dates[0]
        except Exception:
            # Do not turn one optional history-enrichment failure into a failed
            # collector. The current version date remains valid as event_date.
            pass
        cache[doi] = first
        return first

    def _collect_native(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        cursor = 0
        seen = 0
        relevant: list[RawItem] = []
        saturated = False
        first_public_cache: dict[str, str] = {}
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
                    first_public = self._first_public_date(rec, http=http, cache=first_public_cache)
                    relevant.append(RawItem(
                        stable_id=doi, title=title,
                        url=f"https://www.{self.server}.org/content/{doi}" if doi else "",
                        published_date=pubdate, event_date=pubdate, first_public_at=first_public,
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

    def _collect_europe_pmc(
        self,
        *,
        source: SourceSpec,
        window: Window,
        max_results: int,
        http,
        native_error: Exception,
    ) -> CollectorOutcome:
        """Bounded secondary fallback when the native openRxiv API is unavailable.

        Europe PMC indexes bioRxiv/medRxiv preprints and exposes the preprint
        platform as ``bookOrReportDetails.publisher``. The API-side PUBLISHER
        filter keeps source attribution explicit. Europe PMC is nevertheless a
        secondary index and may lag the native server, and FIRST_PDATE does not
        represent native revision events; therefore fallback coverage is always
        reported as ``partial`` even when every indexed result was scanned.
        """
        query = (
            f'SRC:PPR AND PUBLISHER:"{self.europe_pmc_publisher}" '
            f'AND FIRST_PDATE:[{window.start.isoformat()} TO {window.end.isoformat()}]'
        )
        cursor_mark = "*"
        total: int | None = None
        seen = 0
        relevant: list[RawItem] = []
        saturated = False

        while True:
            payload = http.json(
                self.europe_pmc_base,
                params={
                    "query": query,
                    "resultType": "core",
                    "pageSize": self.europe_pmc_page_size,
                    "format": "json",
                    "sort": "FIRST_PDATE_D desc",
                    "cursorMark": cursor_mark,
                },
            )
            if total is None:
                try:
                    total = int(payload.get("hitCount", 0) or 0)
                except (TypeError, ValueError):
                    total = 0
            records = ((payload.get("resultList") or {}).get("result") or [])
            seen += len(records)

            for rec in records:
                publisher = str(((rec.get("bookOrReportDetails") or {}).get("publisher") or "")).strip()
                if publisher.lower() != self.europe_pmc_publisher.lower():
                    continue
                doi = str(rec.get("doi") or "").strip()
                title = str(rec.get("title") or "").strip()
                abstract = str(rec.get("abstractText") or "").strip()
                pubdate = str(rec.get("firstPublicationDate") or "").strip()
                # DOI/date are required to preserve stable native attribution and
                # deterministic time-window semantics in the fallback path.
                if not doi or not title or not pubdate:
                    continue
                if local_relevance(f"{title}\n{abstract}", source.query_template):
                    relevant.append(RawItem(
                        stable_id=doi,
                        title=title,
                        url=f"https://www.{self.server}.org/content/{doi}",
                        published_date=pubdate,
                        event_date=pubdate,
                        first_public_at=pubdate,
                        snippet=abstract[:1200],
                        notes="metadata_source=europepmc_fallback;native_openrxiv_unavailable",
                    ))
                    if len(relevant) >= max_results:
                        saturated = True
                        break

            if saturated:
                break
            if not records or (total is not None and seen >= total):
                break
            next_cursor = str(payload.get("nextCursorMark") or "").strip()
            if not next_cursor or next_cursor == cursor_mark:
                # The server reported additional hits but did not provide a usable
                # cursor. Preserve truthful partial coverage rather than looping.
                break
            cursor_mark = next_cursor

        relevant = relevant[:max_results]
        note = (
            f"native_failure={type(native_error).__name__};fallback=europepmc;"
            f"fallback_results_seen={seen};fallback_total={total if total is not None else ''};"
            "coverage_limitation=first_publications_only"
        )
        return CollectorOutcome(
            collector_id=self.collector_id,
            source_id=self.source_id,
            channel_id=self.channel_id,
            execution_status="partial",
            saturation_status="saturated" if saturated else "clear",
            results_seen=seen,
            relevant_items=relevant,
            representative_url=relevant[0].url if relevant else "",
            failure_reason="native_openrxiv_failed_europepmc_fallback",
            diagnostic_note=note,
            fallback_used=True,
        )

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        try:
            return self._collect_native(source=source, window=window, max_results=max_results, http=http)
        except Exception as native_error:
            try:
                return self._collect_europe_pmc(
                    source=source,
                    window=window,
                    max_results=max_results,
                    http=http,
                    native_error=native_error,
                )
            except Exception as fallback_error:
                raise fallback_error from native_error
