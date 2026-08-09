# Sprint 3A — Shadow Reasoning Worker Contract

This document defines the public, content-free interface between deterministic discovery and the private reasoning worker. It intentionally excludes private prompts, entity lists, query terms, source strategy, report content, and spreadsheet locators.

## Purpose

Sprint 3A proves the middle layer of the v11 pipeline without producing a report:

`active Signals -> event clustering -> bounded verification -> Candidates + one shadow Run attempt`

The reasoning itself is executed in a private ChatGPT context. The public repository supplies only deterministic identifiers, state validation, referential checks, and a manual validation workflow.

## Ownership boundary

During Sprint 3A the worker may read:

- active `Lite_Signals` for the target shadow `run_key`
- current-run `Lite_SourceCoverage`
- recent reported history needed for novelty checks
- prior/due Candidate state needed for pending follow-up
- active private configuration

During Sprint 3A the worker may write only:

- `Lite_Candidates` rows that actually entered verification and received a disposition
- one `Lite_Runs` row for the current shadow attempt

The worker MUST NOT write current-run rows to:

- `Lite_DailyItems`
- `Lite_EventIndex`

It MUST NOT mark a Sprint 3A attempt `passed`, MUST NOT set `canonical_attempt`, and MUST NOT change production execution mode.

## Attempt semantics

A shadow attempt ID is fully qualified:

`<shadow-run-key>-A1`, `<shadow-run-key>-A2`, ...

Attempts are append-only. A later attempt does not overwrite an earlier one. Sprint 3A completion is represented by `state_status=verified`, `delivery_status=not_started`, and `schema_version=v11.0` after Candidate write/readback succeeds.

## Candidate contract

`Lite_Candidates` contains only event-level objects that actually entered verification. A Candidate must reference one or more active `signal_id` values from the same shadow run.

Each Candidate requires at minimum:

- deterministic `candidate_id`
- `run_key` and fully-qualified `attempt_id`
- `source_signal_ids`
- `event_key_v11`
- `delta_key`
- `priority_class`
- final current disposition
- `schema_version=v11.0`

Candidate dispositions remain the existing schema enum: `selected`, `rejected`, `pending`, `expired`, `superseded`. Sprint 3A does not add a public `queued` state.

A `pending` Candidate is allowed only for P0/P1 and must include `pending_type`, `missing_evidence`, `retry_after`, and `expiry_date`.

## Event and delta identity

The private worker applies the v11 semantic definitions already stored in private state. The public validator treats `event_key_v11` and `delta_key` as opaque identifiers and never reconstructs private business rules from them.

Within one attempt, `candidate_id` and `delta_key` must be unique. Several source Signals may support one Candidate.

## Coverage metadata

Collector execution and source saturation remain distinct concepts. The public validator derives only two operational counts from current-run `Lite_SourceCoverage`:

- `collector_failure_count`
- `collector_saturation_count`

These must match the corresponding shadow Run fields. A saturated source is not automatically a failed source.

## Readback gate

The manual `Shadow Worker State Validation` workflow fails closed if any of the following is true:

- target run is not a shadow run
- no worker attempt exists
- there is not exactly one Run row for the chosen attempt
- Run is not `verified`
- Run is already canonical or delivery has started
- Run candidate count differs from actual Candidate rows
- Candidate IDs or delta keys collide within the attempt
- a Candidate references a non-active Signal
- a pending Candidate violates the pending contract
- collector diagnostics disagree with the Run row
- Sprint 3A has written current-run DailyItems or EventIndex state

The workflow logs only compact operational counts/error labels. It must not publish raw Signals, Candidate content, private configuration, spreadsheet identifiers, or report bodies as logs or artifacts.

## Security and deployment

- GitHub Actions uses OIDC/WIF only; no long-lived Google key.
- The private spreadsheet locator remains an Actions secret.
- PR CI does not receive Google identity tokens.
- The validation workflow is manual-only during Sprint 3A.
- No OpenAI API key is added to the public repository.
- The existing production v10.5 scheduled task remains unchanged until a later explicit cutover.

## Exit criteria for Sprint 3A

Sprint 3A is considered validated only after a real shadow worker attempt has:

1. consumed active Signals from a collector-backed shadow run;
2. produced a bounded, event-level Candidate set with traceable source Signals;
3. written one non-canonical `verified` Run attempt;
4. passed centralized readback via `Shadow Worker State Validation`;
5. left current-run DailyItems and EventIndex untouched.

Only then should the project proceed to Coverage Gate/Rescue and final selection/freeze work.
