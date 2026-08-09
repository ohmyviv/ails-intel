from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

ALLOWED_FIELDS = {
    "event", "component", "stage", "status", "run_key", "attempt_id",
    "producer_id", "channel_id", "collector_id", "execution_status",
    "coverage_confidence", "rows_found", "healthy_rows", "error_code",
    "error_count", "check_count", "elapsed_ms",
}


def log_event(event: str, **fields) -> None:
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"unsafe log fields requested: {sorted(unknown)}")
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stdout)
