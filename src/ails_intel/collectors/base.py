from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from ails_intel.http_client import HttpClient
from ails_intel.models import CollectorOutcome, SourceSpec

@dataclass(frozen=True)
class Window:
    start: date
    end: date

class Collector(Protocol):
    collector_id: str
    source_id: str
    channel_id: str
    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http: HttpClient) -> CollectorOutcome:
        ...
