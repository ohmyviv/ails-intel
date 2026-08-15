from __future__ import annotations

import calendar
import time
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


def _publication_types(article) -> set[str]:
    return {
        _node_text(node).casefold()
        for node in article.findall("./MedlineCitation/Article/PublicationTypeList/PublicationType")
        if _node_text(node)
    }


def _contains_any(text: str, terms: list[str]) -> bool:
    hay = (text or "").casefold()
    return any(str(term).strip().casefold() in hay for term in terms if str(term).strip())


class PubMedCollector:
    collector_id = "COL-PUBMED"
    source_id = "SRC-040"
    channel_id = "C5"
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    # PubMed ESearch retrieval is bounded at 10,000 records. Keep the same
    # ceiling for one daily date-bounded collector run, and report partial
    # coverage if the source window ever exceeds it rather than pretending the
    # first page is complete.
    default_scan_budget = 10_000
    default_fetch_batch_size = 200
    default_request_interval_seconds = 0.36

    def __init__(
        self,
        *,
        gate_options: dict[str, object] | None = None,
        scan_budget: int | None = None,
        fetch_batch_size: int | None = None,
        request_interval_seconds: float | None = None,
        sleep_fn=None,
    ):
        self.gate = dict(gate_options or {})
        self.scan_budget = max(1, min(int(scan_budget or self.default_scan_budget), 10_000))
        self.fetch_batch_size = max(1, min(int(fetch_batch_size or self.default_fetch_batch_size), 1_000))
        self.request_interval_seconds = max(
            0.0,
            float(
                self.default_request_interval_seconds
                if request_interval_seconds is None
                else request_interval_seconds
            ),
        )
        self._sleep = sleep_fn or time.sleep

    def _item_from_article(self, article, *, source: SourceSpec, window: Window, counters: dict[str, int]) -> RawItem | None:
        pmid = (article.findtext("./MedlineCitation/PMID") or "").strip()
        title = _node_text(article.find("./MedlineCitation/Article/ArticleTitle"))
        abstract_parts = []
        abstract_labels = []
        for node in article.findall("./MedlineCitation/Article/Abstract/AbstractText"):
            label = (node.attrib.get("Label") or "").strip()
            text = _node_text(node)
            if label:
                abstract_labels.append(label)
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abstract_parts).strip()
        combined = f"{title}\n{abstract}"
        if not local_relevance(combined, source.query_template):
            counters["filtered_local"] += 1
            return None

        if bool(self.gate.get("enabled", False)):
            pub_types = _publication_types(article)
            excluded = {
                str(x).strip().casefold()
                for x in (self.gate.get("exclude_publication_types") or [])
                if str(x).strip()
            }
            if pub_types & excluded:
                counters["filtered_pubtype"] += 1
                return None

            if bool(self.gate.get("require_original_contribution", False)):
                strong_types = {
                    str(x).strip().casefold()
                    for x in (self.gate.get("strong_original_publication_types") or [])
                    if str(x).strip()
                }
                original_markers = [str(x) for x in (self.gate.get("original_markers") or [])]
                structured_labels = {
                    str(x).strip().casefold()
                    for x in (self.gate.get("original_abstract_labels") or [])
                    if str(x).strip()
                }
                label_set = {x.casefold() for x in abstract_labels}
                has_original_evidence = bool(pub_types & strong_types)
                has_original_evidence = has_original_evidence or bool(label_set & structured_labels)
                has_original_evidence = has_original_evidence or _contains_any(combined, original_markers)
                if not has_original_evidence:
                    counters["filtered_nonoriginal"] += 1
                    return None

        first_public = _first_public_date(article, window.end)
        if not first_public:
            # The ESearch EDAT window proves the record is newly visible in this
            # interval even when a detailed public-date history is absent. Use
            # the bounded discovery end rather than a potentially future issue.
            first_public = window.end.isoformat()
        return RawItem(
            stable_id=pmid,
            title=title,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            published_date=first_public,
            event_date=first_public,
            first_public_at=first_public,
            snippet=abstract[:1200],
        )

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        query = strip_site_prefix(source.query_template)
        # The output budget (max_results) and discovery scan depth are separate.
        # ESearch posts the full date-bounded set to Entrez History; EFetch then
        # walks that stable set in bounded batches using WebEnv/query_key.
        search = http.json(
            f"{self.base}/esearch.fcgi",
            {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": 0,
                "usehistory": "y",
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
        total = int(result.get("count") or 0)
        webenv = str(result.get("webenv") or result.get("WebEnv") or "").strip()
        query_key = str(result.get("querykey") or result.get("query_key") or result.get("QueryKey") or "").strip()
        if total and (not webenv or not query_key):
            raise RuntimeError("PubMed ESearch history identifiers missing")

        scan_target = min(total, self.scan_budget)
        scanned = 0
        items: list[RawItem] = []
        counters = {"filtered_local": 0, "filtered_pubtype": 0, "filtered_nonoriginal": 0}
        history_incomplete = False
        relevant_budget_exhausted = False

        while scanned < scan_target:
            batch_size = min(self.fetch_batch_size, scan_target - scanned)
            if self.request_interval_seconds:
                self._sleep(self.request_interval_seconds)
            xml = http.text(
                f"{self.base}/efetch.fcgi",
                {
                    "db": "pubmed",
                    "query_key": query_key,
                    "WebEnv": webenv,
                    "retstart": scanned,
                    "retmax": batch_size,
                    "retmode": "xml",
                },
            )
            root = ET.fromstring(xml)
            articles = root.findall("PubmedArticle")
            if not articles:
                history_incomplete = True
                break

            for article in articles:
                item = self._item_from_article(article, source=source, window=window, counters=counters)
                if item is not None and len(items) < max_results:
                    items.append(item)
            scanned += len(articles)

            # Once the output budget is full, scanning more source records cannot
            # emit additional signals. Stop, but truthfully report partial source
            # coverage unless this batch also reached the end of the source set.
            if len(items) >= max_results and scanned < total:
                relevant_budget_exhausted = True
                break

        scan_budget_exhausted = total > self.scan_budget and scanned >= self.scan_budget
        source_complete = scanned >= total and not history_incomplete
        if source_complete:
            execution_status = "complete"
            saturation_status = "clear"
            failure_reason = ""
        elif relevant_budget_exhausted:
            execution_status = "partial"
            saturation_status = "saturated"
            failure_reason = "relevant_budget_exhausted"
        elif scan_budget_exhausted:
            execution_status = "partial"
            saturation_status = "saturated"
            failure_reason = "scan_budget_exhausted"
        else:
            execution_status = "partial"
            saturation_status = "unknown"
            failure_reason = "history_fetch_incomplete"

        diagnostics = ";".join([
            f"source_total={total}",
            f"scanned={scanned}",
            f"scan_budget={self.scan_budget}",
            f"fetch_batch_size={self.fetch_batch_size}",
            f"filtered_local={counters['filtered_local']}",
            f"filtered_pubtype={counters['filtered_pubtype']}",
            f"filtered_nonoriginal={counters['filtered_nonoriginal']}",
        ])
        return CollectorOutcome(
            collector_id=self.collector_id,
            source_id=self.source_id,
            channel_id=self.channel_id,
            execution_status=execution_status,
            saturation_status=saturation_status,
            results_seen=scanned,
            relevant_items=items,
            representative_url=items[0].url if items else "",
            failure_reason=failure_reason,
            diagnostic_note=diagnostics,
        )
