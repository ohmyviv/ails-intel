# Sprint 4.4A.1 — Specialist Sensor Probation

New deterministic feeds should be observable before they become hard transaction dependencies.

## Contract

An enabled structured collector may set `barrier_required=false` in private runtime configuration.

A probation collector:

- still runs in the normal Structured Collectors workflow;
- still writes deterministic `Lite_Signals` and `Lite_SourceCoverage`;
- still participates in final active-Signal snapshot drift checks if it emits Signals;
- does not block Candidate formation solely because its collector Coverage is missing, failed, skipped, or stale;
- remains subject to the same no-leak, idempotency, and ownership rules as every other collector.

Enabled collectors are barrier-required by default. Probation therefore requires an explicit opt-out and cannot accidentally weaken existing core collectors.

## Promotion

A specialist sensor should be promoted to `barrier_required=true` only after repeated natural runs demonstrate a stable endpoint, parseable freshness diagnostics, and acceptable failure rate. Promotion is a private configuration change; no code change is required.

## Rationale

Snapshot Barrier protects reasoning from consuming an incomplete deterministic snapshot. Newly introduced third-party feeds have a different operational risk: an immature endpoint can fail independently of the core data plane. Probation separates *observability* from *transaction criticality* while preserving the stronger rule that every Signal actually emitted must be included in the final accepted reasoning snapshot.