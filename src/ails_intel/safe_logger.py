from __future__ import annotations
import json,sys
from datetime import datetime,timezone
ALLOWED_FIELDS={"event","component","stage","status","run_key","attempt_id","producer_id","channel_id","collector_id","execution_status","coverage_confidence","rows_found","healthy_rows","error_code","error_count","check_count","elapsed_ms","results_seen","signal_count","duplicate_count","reactivated_count","saturation_status","source_id","collection_batch_id","coverage_row_count","route_count","candidate_count","manifest_hash","ledger_verdict","source_failure_path","archive_check","frozen_item_count","structured_signal_count","worker_signal_count","http_status","content_type","response_bytes","attempt_count","root_tag","item_count","entry_count","channel_count","title_count","link_count","date_count","complete_count","child_tags","date_shape","date_length","epmc_hit_count","epmc_result_count","epmc_server_match_count","epmc_doi_count","epmc_title_count","epmc_abstract_count","epmc_date_count","epmc_result_keys","epmc_server_match_paths","fallback_used","report_date","run_type"}
def log_event(event,**fields):
    unknown=set(fields)-ALLOWED_FIELDS
    if unknown: raise ValueError(f"unsafe log fields requested: {sorted(unknown)}")
    print(json.dumps({"ts":datetime.now(timezone.utc).isoformat(timespec="seconds"),"event":event,**fields},ensure_ascii=False,separators=(",",":")),file=sys.stdout)
