from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.collectors.rss import RssCollector, _date, parse_feed
from ails_intel.models import SourceSpec

RSS = """<?xml version='1.0'?>
<rss><channel>
  <item><title>AI drug discovery partnership expands</title><link>https://example.com/a</link><guid>a</guid><pubDate>Mon, 10 Aug 2026 08:00:00 GMT</pubDate><description>Company signs a funding and partnership deal.</description></item>
  <item><title>General biotech manufacturing update</title><link>https://example.com/b</link><guid>b</guid><pubDate>Sun, 09 Aug 2026 08:00:00 GMT</pubDate><description>No artificial intelligence content.</description></item>
  <item><title>Old AI funding</title><link>https://example.com/c</link><guid>c</guid><pubDate>Thu, 30 Jul 2026 08:00:00 GMT</pubDate><description>AI funding.</description></item>
</channel></rss>"""

FIERCE_RSS = """<?xml version='1.0'?>
<rss><channel>
  <item>
    <title>AI biotech discovery update</title>
    <link>https://www.fiercebiotech.com/biotech/example</link>
    <guid>fierce-1</guid>
    <pubDate>Aug 15, 2026 10:47AM</pubDate>
    <description>Artificial intelligence and drug discovery.</description>
  </item>
</channel></rss>"""

ATOM = """<?xml version='1.0' encoding='utf-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <entry>
    <title>AI-guided protein design reaches experimental validation</title>
    <id>tag:example.com,2026:ai-protein</id>
    <link rel='alternate' href='https://example.com/ai-protein'/>
    <updated>2026-08-10T12:30:00Z</updated>
    <summary>Researchers report an AI protein-design system with experimental validation.</summary>
  </entry>
</feed>"""

NAMESPACED_RSS = """<?xml version='1.0'?>
<rss xmlns:dc='http://purl.org/dc/elements/1.1/' xmlns:content='http://purl.org/rss/1.0/modules/content/'><channel>
  <item>
    <title>Hospital deploys ambient AI across clinical workflow</title>
    <link>https://example.com/deployment</link>
    <guid>deployment-1</guid>
    <dc:date>2026-08-10T09:15:00Z</dc:date>
    <content:encoded><![CDATA[Health system deploys ambient AI documentation across hospitals.]]></content:encoded>
  </item>
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


def test_date_parses_fierce_current_rss_shape():
    assert _date("Aug 15, 2026 10:47AM") == "2026-08-15"
    assert _date("August 15, 2026 10:47AM") == "2026-08-15"


def test_parse_feed_supports_fierce_current_pubdate():
    items = parse_feed(FIERCE_RSS)
    assert len(items) == 1
    assert items[0].stable_id == "fierce-1"
    assert items[0].published_date == "2026-08-15"


def test_parse_feed_supports_atom_topic_feeds():
    items = parse_feed(ATOM)
    assert len(items) == 1
    assert items[0].stable_id == "tag:example.com,2026:ai-protein"
    assert items[0].url == "https://example.com/ai-protein"
    assert items[0].published_date == "2026-08-10"
    assert "experimental validation" in items[0].snippet


def test_parse_feed_supports_namespaced_rss_topic_feeds():
    items = parse_feed(NAMESPACED_RSS)
    assert len(items) == 1
    assert items[0].stable_id == "deployment-1"
    assert items[0].published_date == "2026-08-10"
    assert "ambient AI documentation" in items[0].snippet


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
