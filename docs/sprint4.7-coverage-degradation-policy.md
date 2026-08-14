# Sprint 4.7 — Coverage Degradation Policy

## Architecture rule

v11 applies one system-level rule:

> Fail closed on integrity; degrade gracefully on coverage.

No individual source, endpoint, feed, or structured collector may by itself block Worker Search or the downstream reasoning transaction.

## Source failure semantics

A failed collector must still write an auditable `SourceCoverage` failure record. Its failure may:

- lower aggregate coverage confidence;
- mark the affected channel/domain partial or degraded;
- increase Worker Search effort for the affected domain;
- trigger Rescue;
- contribute to a later decision that evidence is insufficient to freeze or publish.

It must not, by itself:

- fail Snapshot Barrier;
- suppress unrelated Worker routes;
- prevent Unified Ingestion from consuming the usable snapshot;
- convert `Verified Candidates = 0` into a misleading claim that no candidates existed.

Legacy per-collector `barrier_required` flags are non-operative for source-level blocking.

## Integrity failures remain fail-closed

The transaction must still stop when the system cannot establish a coherent and auditable state. Examples include invalid execution mode, disabled required writes, unsupported configuration, missing active registry/config state, inconsistent snapshot identity, schema/state corruption, or readback/manifest integrity failure.

These are transaction-integrity failures, not coverage failures.

## Operational consequence

Structured collector batches return a successful process exit when one or more individual sources fail after their failure diagnostics have been persisted. The batch is logged as `DEGRADED`, and downstream Worker Search is expected to continue and compensate where possible.

Aggregate Coverage Gate and Rescue remain responsible for deciding whether the final evidence set is strong enough to freeze. A low-confidence run must not be silently represented as high confidence.

## Regression invariant

A run in which only `COL-BIORXIV` fails must still be allowed to enter Worker Search. The same invariant applies to every other individual source.
