# Sprint 4.8.5 — Scheduled Orchestrator Isolation

This contract separates the two daily transactions while preserving sequential execution against the shared private state store.

## Scope

The daily scheduler may run a production transaction and a Shadow transaction in sequence to avoid concurrent writes. Sequential ordering is write coordination only; it is not a success dependency.

A production outcome MUST NOT, by itself, determine whether Shadow is allowed to start. After production reaches an explicit outcome — success, blocked, terminal failure, or bootstrap/precommit failure — the orchestrator must attempt to establish a fresh, independent Shadow transaction. Shadow is blocked only by its own transaction-establishment or integrity gates, or by a genuinely shared infrastructure failure that prevents Shadow from establishing a legal transaction.

## Production bootstrap heartbeat

Before production discovery or search, the orchestrator must establish durable run identity and an in-progress bootstrap state, then read it back. A production run is not considered legally started until this write/readback succeeds.

If the bootstrap record cannot be durably established, the orchestrator must not claim that production ran, passed, or formed a frozen result. This is a production bootstrap/precommit failure. It terminates production only and does not automatically cancel Shadow.

Existing frozen or committed state remains subject to the existing resume rules and must not be rediscovered or reselected.

## Shadow independence

Shadow uses its own run key, attempt, transaction identity, state transitions, and readbacks. It must independently refresh the current-day Structured persisted state before qualification. Production state is comparison input only; it is not a Shadow integrity gate.

Shadow must retain the existing isolation invariants:

- no mutation of production run rows;
- no write to the formal production event index;
- no production canonical-state mutation;
- no reuse of production discovery state as a substitute for Shadow persisted inputs.

## Runtime authority and configuration boundary

At orchestration start, the runtime records a configuration boundary timestamp. The current attempt is governed by the active runtime configuration and explicit precedence rules that existed at that boundary. Configuration changes made after the attempt starts do not mutate the semantics of the in-flight attempt; they apply only to a later legal attempt.

The scheduler prompt is an orchestration shell, not a second copy of the Worker execution algorithm. A stale embedded algorithm must not override a newer active runtime rule with explicit precedence.

## Worker execution remains Sprint 4.8.4

This Sprint does not relax Worker integrity. The Sprint 4.8.4 event-sourced execution contract remains authoritative:

`tool response -> durable execution event -> fsync/readback -> sealed route -> deterministic route summary -> Worker Audit -> Worker Signals -> route Coverage`

Execution counts are derived from sealed events, not reconstructed from chat context or post-hoc memory. Missing or inconsistent execution events fail G2 closed. G3 and Candidate formation remain forbidden until the required Worker journal and downstream reconciliation pass.

The former in-memory route-bundle reconstruction and memory-based persistence-only retry semantics are superseded.

## Deployment hygiene

Normal scheduled-operation changes should be frozen shortly before the daily trigger and remain frozen until the automation reaches a terminal state. An emergency change during this window must not change the configuration boundary of an already-started attempt; it applies to the next legal attempt and should be recorded in the private operational handoff.

## Historical evidence

Historical failed or frozen runs are immutable. This contract must not be used to backfill missing run rows, Worker evidence, Candidates, frozen items, or event-index entries into a historical attempt. A post-fix replay, if authorized, uses a new attempt identity.

## Acceptance

Deployment acceptance requires all of the following:

1. active private runtime configuration contains the isolation and bootstrap rules and passes readback;
2. the daily scheduler has been updated and read back with no stale memory-reconstruction semantics;
3. historical incident rows remain unchanged;
4. a later natural run or explicitly authorized replay independently demonstrates the new orchestration behavior.

Configuration deployment, documentation, CI, or a manual explanation alone do not constitute natural end-to-end acceptance.
