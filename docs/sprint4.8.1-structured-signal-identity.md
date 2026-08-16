# Sprint 4.8.1 — Structured Signal Identity Reconciliation

## Trigger

The 2026-08-16 natural Shadow attempt was blocked before Worker Search because the structured Coverage ledger declared 159 relevant Signals while fresh-read active structured Signals contained 158. The discrepancy localized to bioRxiv: 43 raw relevant observations versus 42 active persisted Signals.

The public collector write path exposed a semantic mismatch: `Coverage.relevant_signal_count` was derived from `len(outcome.relevant_items)` before deterministic `signal_key` deduplication, while `Lite_Signals` persisted only unique/current active Signal identities.

## Contract

This sprint separates observation count from durable Signal count without changing the Sheet schema:

- `hit_count` remains the raw relevant-observation count returned by the collector.
- `relevant_signal_count` means unique active Signals actually persisted for that structured route in the current run snapshot.
- Before Coverage is written, the collector runner fresh-reads active Signals and reconciles the expected `signal_key` set against the persisted set.
- A duplicate raw observation that resolves to an already-active deterministic `signal_key` does not create a second Signal and does not create a false integrity failure.
- A true missing, unexpected, duplicate, or malformed persisted Signal identity remains fail-closed.
- Collector `complete`, `partial`, `failed`, and `skipped` semantics remain coverage-quality states. A retrieval failure is not reclassified as a transaction-integrity failure.

## Two independent defenses

### Write-path reconciliation

The collector runner snapshots existing active structured Signal identities, tracks the expected route-level identity set while processing new observations, writes/reactivates Signals, then fresh-reads the ledger.

Coverage is written only after the expected set exactly matches the persisted set. `relevant_signal_count` is then assigned from the persisted unique set.

This prevents a genuine write loss from being hidden by simply lowering Coverage to the readback count.

### Snapshot Barrier reconciliation

`validate_structured_snapshot_barrier` can additionally receive active Signal rows and compare each structured Coverage row against the unique active `signal_key` set for the same `(producer_id, channel_id, route_id, source_id)` identity.

The comparison is route-level rather than aggregate-only, so equal global totals cannot hide a missing Signal on one route and an unexpected Signal on another.

## Deterministic digest

`structured_signal_set_digest()` provides an order-independent SHA-256 digest of a Signal-key set for safe diagnostics and future persisted fingerprinting. This sprint does not add a new Sheet column; the durable correctness gate is the exact key-set reconciliation itself.

## Regression expectations

The test suite covers:

- 43 raw observations containing one duplicate identity -> 42 unique persisted Signals, with `hit_count=43` and `relevant_signal_count=42`.
- 43 genuinely unique expected Signals with only 42 persisted -> fail-closed identity mismatch.
- Per-route mismatch that would be invisible to a global count-only comparison.
- Duplicate active `signal_key` rows -> integrity failure.
- Terminal collector failure with zero Signals -> coverage degradation, not identity failure.
- Deterministic Signal-set digest behavior.

## Historical evidence

The 2026-08-16 attempt remains immutable evidence of the pre-fix accounting defect. This sprint does not backfill, edit, or manufacture the missing historical Signal and does not modify formal production EventIndex state.

Natural acceptance remains prospective: the next valid Shadow must pass Structured Signal identity reconciliation before Worker Search can provide the still-pending Sprint 4.7.2 / 4.8 runtime evidence.
