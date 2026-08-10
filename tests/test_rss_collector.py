from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.collectors.rss import RssCollector, parse_feed
from ails_intel.models import SourceSpec

RSS = """<?xml version='1.0'?>
<rss><channel>
  <item><title>AI drug discovery partnership expands</title><link>https://example.com/a</link><guid>a</guid><pubDate>Mon, 10 Aug 2026 08:00:00 GMT</pubDate><description>Company signs a funding and partnership deal.</description></item>
  <item><title>General biotech manufacturing update</title><link>https://example.com/b</link><guid>b</guid><pubDate>Sun, 09 Aug 2026 08:00:00 GMT</pubDate><description>No artificial intelligence content.</description></item>
  <item><title>Old AI funding</title><link>https://example.com/c</link><guid>c</guid><pubDate>Thu, 30 Jul 2026 08:00:00 GMT</pubDate><description>AI funding.</description></item>
</channel></rss>"""

STALE_RSS = """<?xml version='1.0'?>
<rss><channel>
  <item><title>AI drug discovery partnership</title><link>https://example.com/old</link><guid>old</guid><pubDate>Thu, 30 Jul 2026 08:00:00 GMT</pubDate><description>AI funding partnership.</description></item>
</channel></rss>"""

EMPTY_RSS = "<?xml version='1.0'?><rss><channel></channel></rss>"


class FakeHttp:
    def __init__(self, body=RSS):
        self.body = body

    def text(self, url):
        return self.body


def test_parse_feed_extracts_stable_dated_items():
    items = parse_feed(RSS)
    assert [x.stable_id for x in items] == ["a", "b", "c"]
    assert items[0].published_date == "2026-08-10"


def test_rss_collector_filters_window_and_private_relevance_query():
    collector = RssCollector(
        "https://example.com/feed.xml",
        '(AI OR "machine learning") (funding OR partnership)',
    )
    source = SourceSpec("SRC-X", "Example", "P0", "unused")
    outcome = collector.collect(
        source=source,
        window=Window(date(2026, 8, 9), date(2026, 8, 10)),
        max_results=10,
        http=FakeHttp(),
    )
    assert outcome.execution_status == "complete"
    assert outcome.results_seen == 2
    assert [x.stable_id for x in outcome.relevant_items] == ["a"]
    assert outcome.diagnostic_note == "parsed_count=3;latest_published_date=2026-08-10"


def test_rss_collector_marks_stale_feed_partial_instead_of_complete_no_hit():
    collector = RssCollector("https://example.com/feed.xml", "AI")
    source = SourceSpec("SRC-X", "Example", "P0", "unused")
    outcome = collector.collect(
        source=source,
        window=Window(date(2026, 8, 8), date(2026, 8, 10)),
        max_results=10,
        http=FakeHttp(STALE_RSS),
    )
    assert outcome.execution_status == "partial"
    assert outcome.failure_reason == "stale_feed"
    assert outcome.results_seen == 0
    assert outcome.diagnostic_note == "parsed_count=1;latest_published_date=2026-07-30"


def test_rss_collector_marks_empty_feed_partial():
    collector = RssCollector("https://example.com/feed.xml", "AI")
    source = SourceSpec("SRC-X", "Example", "P0", "unused")
    outcome = collector.collect(
        source=source,
        window=Window(date(2026, 8, 8), date(2026, 8, 10)),
        max_results=10,
        http=FakeHttp(EMPTY_RSS),
    )
    assert outcome.execution_status == "partial"
    assert outcome.failure_reason == "empty_feed"
    assert outcome.diagnostic_note == "parsed_count=0;latest_published_date="
