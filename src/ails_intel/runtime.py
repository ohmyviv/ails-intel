from __future__ import annotations

import re
from datetime import date, datetime

from ails_intel.config_loader import parse_active_config
from ails_intel.models import CollectorSpec, SourceSpec

MANUAL_RUN_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


def load_active_config(store):
    return parse_active_config(store.rows("Lite_Config!A:G"))


def load_source_specs(store, source_ids: set[str]) -> dict[str, SourceSpec]:
    rows = store.rows("SourceRegistry!A:Z")
    if not rows:
        raise RuntimeError("SourceRegistry is empty")
    header = rows[0]
    pos = {h: i for i, h in enumerate(header)}
    required = {"source_id","source_name","priority","query_template","status","completion_criterion","date_window_method","pagination_required"}
    missing = required - set(pos)
    if missing:
        raise RuntimeError(f"SourceRegistry missing columns: {sorted(missing)}")
    out = {}
    for row in rows[1:]:
        row = list(row) + [""] * max(0, len(header)-len(row))
        sid = str(row[pos["source_id"]]).strip()
        if sid not in source_ids or str(row[pos["status"]]).strip().lower() != "active":
            continue
        out[sid] = SourceSpec(
            source_id=sid,
            source_name=str(row[pos["source_name"]]).strip(),
            priority=str(row[pos["priority"]]).strip() or "P2",
            query_template=str(row[pos["query_template"]]).strip(),
            completion_criterion=str(row[pos["completion_criterion"]]).strip(),
            date_window_method=str(row[pos["date_window_method"]]).strip(),
            pagination_required=str(row[pos["pagination_required"]]).strip().lower() in {"true","1","yes"},
        )
    missing_ids = source_ids - set(out)
    if missing_ids:
        raise RuntimeError(f"active SourceRegistry entries missing: {sorted(missing_ids)}")
    return out


def collector_specs(cfg) -> list[CollectorSpec]:
    raw = cfg["structured_collectors_json"].value
    reserved = {"id", "source_id", "channel_id", "enabled"}
    return [
        CollectorSpec(
            collector_id=str(x["id"]),
            source_id=str(x["source_id"]),
            channel_id=str(x["channel_id"]),
            enabled=bool(x.get("enabled", True)),
            options={str(k): v for k, v in x.items() if k not in reserved},
        )
        for x in raw
        if bool(x.get("enabled", True))
    ]


def build_run_key(cfg, now_bjt: datetime) -> str:
    mode = str(cfg["execution_mode"].value)
    if mode not in {"shadow", "production"}:
        raise RuntimeError("invalid execution_mode")
    prefix_key = "shadow_run_prefix" if mode == "shadow" else "production_run_prefix"
    prefix = str(cfg[prefix_key].value)
    h = int(float(cfg["report_cutoff_hour_bjt"].value))
    m = int(float(cfg["report_cutoff_minute_bjt"].value))
    return f"{prefix}-{now_bjt:%Y%m%d}-{h:02d}{m:02d}-BJT"


def resolve_report_date(report_date: str, now_bjt: datetime) -> date:
    value = str(report_date or "").strip()
    if not value:
        return now_bjt.date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RuntimeError("invalid report_date; expected YYYY-MM-DD") from exc


def resolve_run_key(cfg, now_bjt: datetime, manual_run_key: str = "") -> str:
    """Resolve scheduled or isolated manual run identity.

    Scheduled execution remains config-derived. A manual override is allowed only
    in Shadow mode and must live outside both the scheduled Shadow prefix and the
    production prefix, so a diagnostic rerun cannot overwrite either ledger.
    """
    override = str(manual_run_key or "").strip()
    if not override:
        return build_run_key(cfg, now_bjt)

    if str(cfg["execution_mode"].value) != "shadow":
        raise RuntimeError("manual run_key override requires shadow mode")
    if not MANUAL_RUN_KEY_RE.fullmatch(override):
        raise RuntimeError("invalid manual run_key")

    shadow_prefix = str(cfg["shadow_run_prefix"].value).strip()
    production_entry = cfg.get("production_run_prefix")
    production_prefix = str(production_entry.value).strip() if production_entry is not None else ""
    forbidden_prefixes = {prefix for prefix in (shadow_prefix, production_prefix) if prefix}
    if any(override == prefix or override.startswith(prefix + "-") for prefix in forbidden_prefixes):
        raise RuntimeError("manual run_key must use an isolated namespace")
    return override


def collector_window_days(cfg, channel_id: str) -> int:
    if channel_id == "C1":
        entry = cfg.get("c1_search_window_hours")
        hours = float(entry.value) if entry is not None else 48.0
        return max(1, int((hours + 23) // 24))
    key = "technical_window_days" if channel_id == "C5" else "backfill_window_days"
    return int(float(cfg[key].value))
