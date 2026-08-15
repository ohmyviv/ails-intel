from datetime import date
from types import SimpleNamespace

import pytest

from ails_intel.collector_diagnostics import (
    DEFAULT_DIAGNOSTIC_COLLECTORS,
    _diagnostic_fields,
    _xml_structure_fields,
    diagnostic_probe_targets,
    select_specs,
)
from ails_intel.collectors.base import Window


def _spec(collector_id: str, *, options=None):
    return SimpleNamespace(collector_id=collector_id, options=dict(options or {}))


def test_default_selection_uses_configured_diagnostic_collectors_in_stable_order():
    specs = [
        _spec("COL-PUBMED"),
        _spec("COL-ARXIV"),
        _spec("COL-HITNEWS-AI"),
        _spec("COL-BIORXIV"),
        _spec("COL-MEDRXIV"),
        _spec("COL-FIERCE-RSS"),
    ]
    selected = select_specs(specs, None)
    expected = [collector_id for collector_id in DEFAULT_DIAGNOSTIC_COLLECTORS if collector_id in {s.collector_id for s in specs}]
    assert [spec.collector_id for spec in selected] == expected


def test_all_selection_preserves_configured_order():
    specs = [_spec("COL-PUBMED"), _spec("COL-ARXIV")]
    selected = select_specs(specs, ["all"])
    assert [spec.collector_id for spec in selected] == ["COL-PUBMED", "COL-ARXIV"]


def test_explicit_selection_preserves_request_order_and_deduplicates():
    specs = [_spec("COL-PUBMED"), _spec("COL-BIORXIV")]
    selected = select_specs(specs, ["COL-BIORXIV", " COL-PUBMED ", "COL-BIORXIV"])
    assert [spec.collector_id for spec in selected] == ["COL-BIORXIV", "COL-PUBMED"]


def test_unknown_collector_is_rejected():
    with pytest.raises(ValueError):
        select_specs([_spec("COL-PUBMED")], ["COL-NOT-CONFIGURED"])


class _FakeHttp:
    def __init__(self, attempts):
        self.attempts = attempts

    def diagnostic_log_fields(self):
        return {
            "http_status": 200,
            "content_type": "application/json",
            "response_bytes": 42,
            "attempt_count": self.attempts,
        }


def test_success_diagnostics_only_surface_when_retry_happened():
    assert _diagnostic_fields(_FakeHttp(1)) == {}
    assert _diagnostic_fields(_FakeHttp(2))["attempt_count"] == 2


def test_hitnews_probe_strips_rss_query_from_topic_page():
    spec = _spec(
        "COL-HITNEWS-AI",
        options={"feed_url": "https://www.healthcareitnews.com/topics/artificial-intelligence?format=rss"},
    )
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    assert diagnostic_probe_targets(spec, window) == [
        ("html_topic_probe", "https://www.healthcareitnews.com/topics/artificial-intelligence")
    ]


def test_fierce_probe_checks_configured_and_all_stories_feeds():
    spec = _spec(
        "COL-FIERCE-RSS",
        options={"feed_url": "https://www.fiercebiotech.com/rss/biotech/xml"},
    )
    window = Window(date(2026, 8, 12), date(2026, 8, 15))
    assert diagnostic_probe_targets(spec, window) == [
        ("configured_feed_probe", "https://www.fiercebiotech.com/rss/biotech/xml"),
        ("all_stories_feed_probe", "https://www.fiercebiotech.com/rss/xml"),
    ]


def test_xml_structure_fields_counts_feed_nodes():
    fields = _xml_structure_fields("<rss><channel><item/><item/></channel></rss>")
    assert fields == {"root_tag": "rss", "item_count": 2, "entry_count": 0, "channel_count": 1}


def test_openrxiv_probe_uses_explicit_json_and_xml_formats():
    window = Window(date(2026, 8, 8), date(2026, 8, 15))
    for collector_id, server in (("COL-BIORXIV", "biorxiv"), ("COL-MEDRXIV", "medrxiv")):
        targets = diagnostic_probe_targets(_spec(collector_id), window)
        base = f"https://api.biorxiv.org/details/{server}/2026-08-08/2026-08-15/0"
        assert targets == [
            ("explicit_json_probe", f"{base}/json"),
            ("explicit_xml_probe", f"{base}/xml"),
        ]
