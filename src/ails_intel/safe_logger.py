from __future__ import annotations
import json,sys
from datetime import datetime,timezone
ALLOWED_FIELDS={"event","component","stage","status","run_key","attempt_id","producer_id","channel_id","collector_id","execution_status","coverage_confidence","rows_found","healthy_rows","error_code","error_count","check_count","elapsed_ms","results_seen","signal_count","duplicate_count","reactivated_count","saturation_status","source_id","collection_batch_id","coverage_row_count","route_count","candidate_count","manifest_hash","ledger_verdict","source_failure_path","archive_check","frozen_item_count","structured_signal_count","worker_signal_count","http_status","content_type","response_bytes","attempt_count"}
def log_event(event,**fields):
    unknown=set(fields)-ALLOWED_FIELDS
    if unknown: raise ValueError(f"unsafe log fields requested: {sorted(unknown)}")
    print(json.dumps({"ts":datetime.now(timezone.utc).isoformat(timespec="seconds"),"event":event,**fields},ensure_ascii=False,separators=(",",":")),file=sys.stdout)
