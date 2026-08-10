from __future__ import annotations

from collections.abc import Mapping


_FALSE_VALUES = {False, "FALSE", "false", 0, "0"}


def barrier_required_structured_collector_ids(cfg: Mapping[str, object]) -> set[str]:
    """Return enabled structured collectors that are hard Snapshot Barrier inputs.

    New deterministic sensors may run in probation with ``barrier_required=false``.
    They still emit Signals and SourceCoverage, but a transient endpoint failure does
    not block the whole reasoning transaction until the sensor has demonstrated
    operational stability. The default remains fail-closed: enabled collectors are
    barrier-required unless the private runtime config explicitly opts them out.
    """
    out: set[str] = set()
    raw = cfg.get("structured_collectors_json", []) or []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        collector_id = str(item.get("id", "")).strip()
        enabled = item.get("enabled", True)
        barrier_required = item.get("barrier_required", True)
        if (
            collector_id
            and enabled not in _FALSE_VALUES
            and barrier_required not in _FALSE_VALUES
        ):
            out.add(collector_id)
    return out
