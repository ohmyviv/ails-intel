# Sprint 4.7 — Coverage Degradation Policy

## Architecture rule

v11 applies one system-level rule:

> Fail closed on integrity; degrade gracefully on coverage.

No individual source, endpoint, feed, or structured collector may by itself block Worker Search or the downstream reasoning transaction.

## Snapshot Barrier means terminal observation, not retrieval success

Snapshot Barrier protects the identity and completeness of the reasoning snapshot. For every enabled structured collector, the current run must contain exactly one fresh collector-level coverage diagnostic at or after the configured barrier clock.

The following are terminal observations and therefore satisfy Snapshot Barrier integrity:

- `complete`
- `partial`
- `failed`
- `skipped`

`failed` and `skipped` remain visible as degraded coverage and may trigger additional Worker/Rescue effort. They do not by themselves veto the transaction.

The following remain fail-closed integrity errors:

- missing collector observation;
- duplicate/inconsistent collector observations;
- malformed or empty/non-terminal execution status;
- invalid timestamp;
- stale/wrong-date observation;
- reasoning/final signal-set drift.

Legacy per-collector `barrier_required` flags no longer grant an individual source a transaction veto. The compatibility observation set is all enabled structured collectors.

## Source failure semantics

A failed collector must still write an auditable `SourceCoverage` failure record. Its failure may:

- lower aggregate coverage confidence;
- mark the affected channel/domain partial or degraded;
- increase Worker Search effort for the affected domain;
- trigger Rescue;
- remain visible in the final report as a LOW/MEDIUM coverage limitation.

It must not, by itself:

- fail Snapshot Barrier;
- suppress unrelated Worker routes;
- prevent Unified Ingestion from consuming the usable snapshot;
- block Candidate verification, Freeze, or report generation;
- convert `Verified Candidates = 0` into a misleading claim that no candidates existed.

## Coverage versus item evidence

Coverage confidence and item evidentiary sufficiency are separate decisions.

A LOW coverage run may continue through Rescue, Freeze, and report generation, provided the selected items themselves satisfy the evidence, provenance, manifest, and readback contracts. Coverage weakness must be disclosed; it must not be silently upgraded.

An individual candidate may still be rejected or held pending when its own evidence is insufficient. That is an item-level verification outcome, not a source-level pipeline veto.

## Integrity failures remain fail-closed

The transaction must still stop when the system cannot establish a coherent and auditable state. Examples include invalid execution mode, disabled required writes, unsupported configuration, missing active registry/config state, missing/stale/duplicate collector observation, inconsistent snapshot identity, schema/state corruption, signal-set drift, or readback/manifest integrity failure.

These are transaction-integrity failures, not coverage failures.

## Operational consequence

Structured collector batches return a successful process exit when one or more individual sources fail after their failure diagnostics have been persisted. The batch is logged as `DEGRADED`, and downstream Worker Search is expected to continue and compensate where possible.

Coverage Gate remains responsible for classifying coverage as HIGH/MEDIUM/LOW and triggering bounded Rescue. It validates that the recorded coverage counts are internally consistent, but coverage quality alone does not stop the transaction.

The scheduled Shadow watchdog prospectively enforces the continuation invariant from 2026-08-15 onward: when a completed Shadow has a fresh terminal structured snapshot containing one or more failed/skipped collectors, at least one Worker/Rescue coverage row must exist. The frozen 2026-08-14 incident is retained as historical evidence and is not retroactively reclassified.

## Regression invariants

- A run in which only `COL-BIORXIV` fails must still enter Worker Search.
- The same invariant applies to every other individual source.
- A fresh `failed` collector row satisfies Snapshot Barrier integrity but degrades coverage.
- Missing, stale, duplicate or non-terminal collector observation fails Snapshot Barrier.
- A LOW post-Rescue coverage run may still enter Freeze when its state is internally consistent.
- Freeze must validate selected-item and manifest integrity independently of coverage confidence.
- A completed post-rollout Shadow with terminal source failure and zero Worker/Rescue coverage is a watchdog failure.
