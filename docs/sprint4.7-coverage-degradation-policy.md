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
- remain visible in the final report as a LOW/MEDIUM coverage limitation.

It must not, by itself:

- fail Snapshot Barrier;
- suppress unrelated Worker routes;
- prevent Unified Ingestion from consuming the usable snapshot;
- block Candidate verification, Freeze, or report generation;
- convert `Verified Candidates = 0` into a misleading claim that no candidates existed.

Legacy per-collector `barrier_required` flags are non-operative for source-level blocking.

## Coverage versus item evidence

Coverage confidence and item evidentiary sufficiency are separate decisions.

A LOW coverage run may continue through Rescue, Freeze, and report generation, provided the selected items themselves satisfy the evidence, provenance, manifest, and readback contracts. Coverage weakness must be disclosed; it must not be silently upgraded.

An individual candidate may still be rejected or held pending when its own evidence is insufficient. That is an item-level verification outcome, not a source-level pipeline veto.

## Integrity failures remain fail-closed

The transaction must still stop when the system cannot establish a coherent and auditable state. Examples include invalid execution mode, disabled required writes, unsupported configuration, missing active registry/config state, inconsistent snapshot identity, schema/state corruption, or readback/manifest integrity failure.

These are transaction-integrity failures, not coverage failures.

## Operational consequence

Structured collector batches return a successful process exit when one or more individual sources fail after their failure diagnostics have been persisted. The batch is logged as `DEGRADED`, and downstream Worker Search is expected to continue and compensate where possible.

Coverage Gate remains responsible for classifying coverage as HIGH/MEDIUM/LOW and triggering bounded Rescue. It validates that the recorded coverage counts are internally consistent, but coverage quality alone does not stop the transaction.

## Regression invariants

- A run in which only `COL-BIORXIV` fails must still enter Worker Search.
- The same invariant applies to every other individual source.
- A LOW post-Rescue coverage run may still enter Freeze when its state is internally consistent.
- Freeze must validate selected-item and manifest integrity independently of coverage confidence.
