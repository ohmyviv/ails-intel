from __future__ import annotations

from collections.abc import Mapping


def barrier_required_structured_collector_ids(cfg: Mapping[str, object]) -> set[str]:
    """Return structured collectors that may individually block Snapshot Barrier.

    v11 follows the architecture rule: fail closed on integrity, degrade gracefully
    on coverage. No individual source or collector is a hard barrier input. A source
    failure must remain visible in SourceCoverage and may lower coverage confidence,
    trigger Worker/Rescue compensation, or ultimately prevent freeze when aggregate
    evidence is inadequate, but it must not by itself stop Worker Search.

    ``cfg`` is retained in the signature for compatibility with the private runtime.
    Legacy ``barrier_required`` flags are intentionally ignored.
    """
    del cfg
    return set()
