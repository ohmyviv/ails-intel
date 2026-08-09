from __future__ import annotations
import json
from dataclasses import dataclass

TRUE_VALUES = {"TRUE","true","1","yes","YES"}

@dataclass(frozen=True)
class ConfigEntry:
    key: str
    value: object
    value_type: str

def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip() in TRUE_VALUES

def parse_active_config(rows: list[list[object]]) -> dict[str, ConfigEntry]:
    if not rows:
        raise ValueError("Lite_Config is empty")
    header = [str(x) for x in rows[0]]
    pos = {name:i for i,name in enumerate(header)}
    required = {"config_key","config_value","value_type","active"}
    if not required.issubset(pos):
        raise ValueError(f"Lite_Config missing columns: {sorted(required-set(pos))}")

    out: dict[str, ConfigEntry] = {}
    for row in rows[1:]:
        row = list(row) + [""] * max(0, len(header)-len(row))
        key = str(row[pos["config_key"]]).strip()
        if not key:
            continue
        if not _truthy(row[pos["active"]]):
            continue
        if key in out:
            raise ValueError(f"duplicate active config_key: {key}")
        raw = row[pos["config_value"]]
        typ = str(row[pos["value_type"]]).strip()
        if typ == "json":
            try:
                value = json.loads(str(raw))
            except Exception as exc:
                raise ValueError(f"invalid JSON config {key}: {exc}") from exc
        elif typ == "number":
            try:
                value = float(raw)
            except Exception as exc:
                raise ValueError(f"invalid numeric config {key}: {raw}") from exc
        elif typ == "boolean":
            value = _truthy(raw)
        elif typ == "enum":
            if not str(raw).strip():
                raise ValueError(f"empty enum config {key}")
            value = str(raw)
        else:
            value = str(raw)
        out[key] = ConfigEntry(key=key, value=value, value_type=typ)
    return out
