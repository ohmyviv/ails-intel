# Manual Shadow Rerun Namespace

## Purpose

A same-day diagnostic rerun must not reuse the scheduled Shadow `run_key`. Reusing the scheduled namespace can mutate historical `Lite_Signals` / `Lite_SourceCoverage` rows and make an earlier blocked attempt inconsistent with the ledger that caused the block.

## Contract

- Scheduled collector execution remains config-derived and unchanged.
- Manual collector execution must provide an explicit isolated `manual_run_key`.
- A manual key is accepted only while `execution_mode=shadow`.
- A manual key is rejected if it uses either the configured scheduled-Shadow prefix or the production prefix.
- `report_date` controls collector date windows and Signal date tokens; collection timestamps remain the actual execution time.
- Reusing the same isolated manual key is allowed for deterministic retry/idempotent recovery. Reusing the scheduled namespace is not.
- Manual reruns remain diagnostic evidence. They do not convert a pending scheduled natural-acceptance gate into a natural PASS.

## GitHub Actions

`Structured Collectors` now treats `workflow_dispatch` as an isolated manual-rerun entry point requiring both `manual_run_key` and `report_date`.

When a workflow-dispatch client is unavailable, an explicit update of `.github/manual-structured-rerun.trigger` on `main` provides a bootstrap path. That path derives a same-day `AILS11M-*` run key at execution time, so ordinary code merges do not launch a rerun.

The read-only Shadow acceptance validator also accepts an explicit `--run-key`, allowing a completed manual namespace to be checked without pretending it is the canonical scheduled run.

## Historical immutability

A diagnostic rerun must never edit the failed scheduled attempt being investigated. The scheduled run, its attempt row, and its pre-fix Coverage/Signal evidence remain immutable forensic evidence.

## Frozen Structured input for downstream-only replay

A downstream-only manual replay may consume a previously persisted scheduled Structured snapshot without rerunning or cloning its collector rows. This is an explicit authorization, not a general relaxation of cross-run referential integrity.

The unified-ingestion validator accepts a frozen Structured input only when all of the following are true:

- the consumer is an isolated manual Shadow identity (`AILS11M-*`);
- the source is a scheduled Shadow identity (`AILS11S-*`);
- source and consumer have the same report-date token;
- the source attempt is fully qualified (`<source_run>-A<n>`);
- the supplied fingerprint matches the fresh-read active `collector/*` Signals plus Structured Coverage for that exact run/attempt;
- only active `collector/*` Signals are imported into the Candidate reference scope.

Source-run `chatgpt/worker` and `chatgpt/rescue` Signals are never inherited. A manual replay therefore uses the scheduled Structured snapshot as immutable upstream input while requiring all Worker/Rescue evidence to belong to the new manual attempt.

If the authorization is missing, incomplete, wrong-day, non-scheduled, or fingerprint-drifted, the validator fails closed and the cross-run Structured Signals remain unavailable to Candidate linkage.

## Pre-contract legacy Structured snapshots

Some immutable historical scheduled snapshots were persisted before Structured collector rows carried attempt-level provenance. Those rows may have a valid scheduled `run_key` while `Lite_Signals.origin_attempt_id` and `Lite_SourceCoverage.attempt_id` are blank. Historical rows must not be backfilled merely to make a replay pass.

`legacy_frozen_replay` provides a separate, explicit compatibility adapter for this case. It does not relax the normal unified-ingestion validator. The adapter may qualify a legacy snapshot only when all of the following are true:

- the source is an `AILS11S-*` scheduled Shadow and the requested source attempt is fully qualified;
- fresh-read durable `Lite_Runs` evidence contains exactly one attempt for that source run, and it is the requested attempt;
- every active source `collector/*` Signal has blank `origin_attempt_id` and every source Structured Coverage row has blank `attempt_id`; mixed old/new provenance fails closed;
- Signal identity is unique and complete, Coverage route identity is unique and complete, and per-route persisted active Signal counts exactly match `relevant_signal_count` using `(producer_id, channel_id, route_id, source_id)`;
- the caller supplies a fingerprint of the historical rows exactly as persisted, and it matches a fresh recomputation;
- source-run Worker/Rescue Signals remain excluded.

On success the adapter creates attempt-qualified copies only in memory and computes the fingerprint expected by the unchanged strict frozen-input validator. It never edits the historical scheduled Run, Signal, Coverage, Candidate, DailyItems, or EventIndex ledgers. Any ambiguity in source attempt identity, provenance, route reconciliation, or fingerprint fails closed.