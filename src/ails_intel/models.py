from __future__ import annotations
from dataclasses import dataclass, field

SIGNAL_HEADERS = [
    "signal_id","run_key","collection_batch_id","producer_id","origin_attempt_id",
    "discovered_at_bjt","channel_id","route_id","source_id","discovery_method",
    "raw_title","raw_snippet","entity_hint","action_hint","asset_hint","event_date_hint",
    "published_at_hint","first_public_at_hint","url","stable_id","signal_key",
    "event_key_hint","priority_hint","ai_core_hint","life_science_core_hint",
    "signal_state","notes","schema_version",
]

COVERAGE_HEADERS = [
    "run_key","source_id","source_name","source_group","route","status","hit_count",
    "representative_url","failure_reason","checked_at_bjt","fallback_used","notes",
    "retrieval_status","hit_status","coverage_id","attempt_id","producer_id","channel_id",
    "route_id","execution_status","saturation_status","results_seen",
    "relevant_signal_count","schema_version",
]

@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_name: str
    priority: str
    query_template: str
    completion_criterion: str = ""
    date_window_method: str = ""
    pagination_required: bool = True

@dataclass(frozen=True)
class CollectorSpec:
    collector_id: str
    source_id: str
    channel_id: str
    enabled: bool = True
    options: dict[str, object] = field(default_factory=dict)

@dataclass
class RawItem:
    stable_id: str
    title: str
    url: str
    published_date: str = ""
    event_date: str = ""
    snippet: str = ""
    first_public_at: str = ""

@dataclass
class SignalRecord:
    values: dict[str, object]
    def row(self) -> list[object]:
        return [self.values.get(h, "") for h in SIGNAL_HEADERS]

@dataclass
class CoverageRecord:
    values: dict[str, object]
    def row(self) -> list[object]:
        return [self.values.get(h, "") for h in COVERAGE_HEADERS]

@dataclass
class CollectorOutcome:
    collector_id: str
    source_id: str
    channel_id: str
    execution_status: str
    saturation_status: str
    results_seen: int
    relevant_items: list[RawItem] = field(default_factory=list)
    representative_url: str = ""
    failure_reason: str = ""
