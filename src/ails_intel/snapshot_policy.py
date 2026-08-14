from __future__ import annotations

from collections.abc import Mapping


def barrier_required_structured_collector_ids(cfg: Mapping[str, object]) -> set[str]:
    """Return structured collectors that may individually block Snapshot Barrier.

    v11 follows the architecture rule: fail closed on integrity, degrade gracefully
    on coverage. No individual source or collector is a hard barrier input. A source
    failure remains visible in SourceCoverage, may lower coverage confidence, and may
    trigger Worker/Rescue compensation, but coverage quality alone does not stop the
    downstream reasoning, freeze, or report transaction.

    ``cfg`` is retained in the signature for compatibility with the private runtime.
    Legacy ``barrier_required`` flags are intentionally ignored.
    """
    del cfg
    return set()
