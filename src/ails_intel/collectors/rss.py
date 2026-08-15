from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import local_relevance

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(node: ET.Element, names: set[str]) -> str:
    for child in node.iter():
        if _local_name(child.tag) in names:
            value = "".join(child.itertext()).strip()
            if value:
                return value
    return ""


def _link(node: ET.Element) -> str:
    for child in node.iter():
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "")).strip()
        if href:
            rel = str(child.attrib.get("rel", "alternate")).strip().lower()
            if rel in {"", "alternate"}:
                return href
        value = (child.text or "").strip()
        if value:
            return value
    return ""


def _clean_html(value: str) -> str:
    return WS_RE.sub(" ", html.unescape(TAG_RE.sub(" ", value or ""))).strip()


def _date(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        pass
    # Fierce Biotech currently publishes RSS dates like
    # "Aug 15, 2026 10:47AM", which is neither RFC 822/1123 nor ISO 8601.
    # Keep this bounded to explicit human-readable formats rather than using
    # a permissive date parser that could silently reinterpret ambiguous dates.
    for fmt in ("%b %d, %Y %I:%M%p", "%B %d, %Y %I:%M%p"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw) else ""


def parse_feed(xml_text: str) -> list[RawItem]:
    root = ET.fromstring(xml_text)
    nodes = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    out: list[RawItem] = []
    for node in nodes:
        title = _clean_html(_text(node, {"title"}))
        url = _link(node)
        stable_id = _text(node, {"guid", "id"}) or url
        published = _date(_text(node, {"pubdate", "published", "updated", "date"}))
        snippet = _clean_html(_text(node, {"description", "summary", "content", "encoded"}))
        if not title or not url or not published:
            continue
        out.append(
            RawItem(
                stable_id=stable_id,
                title=title,
                url=url,
                published_date=published,
                event_date=published,
                snippet=snippet[:1200],
                first_public_at=published,
            )
        )
    return out


def _diagnostic_note(items: list[RawItem]) -> str:
    if not items:
        return "parsed_count=0;latest_published_date="
    latest = max(item.published_date for item in items)
    return f"parsed_count={len(items)};latest_published_date={latest}"


class RssCollector:
    def __init__(self, feed_url: str, relevance_query: str = ""):
        if not str(feed_url).strip():
            raise ValueError("RSS collector requires feed_url")
        self.feed_url = str(feed_url).strip()
        self.relevance_query = str(relevance_query or "").strip()

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        items = parse_feed(http.text(self.feed_url))
        diagnostic = _diagnostic_note(items)
        if not items:
            return CollectorOutcome(
                collector_id="rss",
                source_id=source.source_id,
                channel_id="",
                execution_status="partial",
                saturation_status="clear",
                results_seen=0,
                relevant_items=[],
                representative_url="",
                failure_reason="empty_feed",
                diagnostic_note=diagnostic,
            )

        start = window.start.isoformat()
        end = window.end.isoformat()
        in_window = [
            item
            for item in items
            if start <= item.published_date <= end
        ]
        if not in_window:
            latest = max(item.published_date for item in items)
            reason = "stale_feed" if latest < start else "date_window_empty"
            return CollectorOutcome(
                collector_id="rss",
                source_id=source.source_id,
                channel_id="",
                execution_status="partial",
                saturation_status="clear",
                results_seen=0,
                relevant_items=[],
                representative_url="",
                failure_reason=reason,
                diagnostic_note=diagnostic,
            )

        query = self.relevance_query or source.query_template
        relevant = [
            item
            for item in in_window
            if local_relevance(f"{item.title} {item.snippet}", query)
        ]
        relevant.sort(key=lambda item: (item.published_date, item.stable_id), reverse=True)
        saturated = len(relevant) > max_results
        selected = relevant[:max_results]
        return CollectorOutcome(
            collector_id="rss",
            source_id=source.source_id,
            channel_id="",
            execution_status="partial" if saturated else "complete",
            saturation_status="saturated" if saturated else "clear",
            results_seen=len(in_window),
            relevant_items=selected,
            representative_url=selected[0].url if selected else "",
            failure_reason="",
            diagnostic_note=diagnostic,
        )
