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

`legacy_frozen_replay` provides a separate, explicit compatibility adapter for this case. It does not relax the normal unified-ingestion validator. The adapter has two provenance modes:

1. **Durable Run ledger mode**: fresh-read `Lite_Runs` evidence contains exactly one attempt for the source run, and it is the requested attempt.
2. **Missing durable Run attestation mode**: fresh-read `Lite_Runs` contains zero attempts for the source run, the caller explicitly supplies `missing_durable_run_ledger_v1`, and the in-memory qualification alias is deterministically `<source_run>-A1`.

The second mode is intentionally narrow. The attestation is an execution-time assertion about fresh-read absence of a historical Run row; it does not create, backfill, or imply that an `A1` Run row ever existed. If any durable attempt is present, attestation mode is forbidden and cannot override mismatched or multiple attempt evidence.

In either provenance mode, the adapter may qualify a legacy snapshot only when all of the following are true:

- the source is an `AILS11S-*` scheduled Shadow and the requested qualification attempt is fully qualified;
- every active source `collector/*` Signal has blank `origin_attempt_id` and every source Structured Coverage row has blank `attempt_id`; mixed old/new provenance fails closed;
- Signal identity is unique and complete, Coverage route identity is unique and complete, and per-route persisted active Signal counts exactly match `relevant_signal_count` using `(producer_id, channel_id, route_id, source_id)`;
- the caller supplies a fingerprint of the historical rows exactly as persisted, and it matches a fresh recomputation;
- source-run Worker/Rescue Signals remain excluded.

On success the adapter creates attempt-qualified copies only in memory and computes the fingerprint expected by the unchanged strict frozen-input validator. The returned `provenance_mode` records whether qualification came from the durable Run ledger or the explicit missing-ledger attestation. The adapter never edits the historical scheduled Run, Signal, Coverage, Candidate, DailyItems, or EventIndex ledgers. Any ambiguity in source attempt identity, provenance, route reconciliation, or fingerprint fails closed.

## Sealed G2 checkpoint continuation into G3

During controlled diagnostic acceptance work, a downstream gate may continue from an already executed and persisted same-attempt G2 checkpoint instead of rerunning Worker discovery. This is intended to isolate downstream contract changes from new search variance.

The G2 -> G3 handoff is read-only. G3 consumes the same-attempt persisted Worker route summaries, Worker Coverage, and active Worker Signals and reconciles them against the route contract. It does not execute searches, open pages, create new Worker Signals, or rewrite historical rows.

The authoritative route universe for this handoff is built as follows:

- current canonical base Worker routes remain the normal contract;
- registry-derived source routes that are due for the report date are valid route-universe extensions when same-attempt persisted route-summary evidence resolves them to exactly one channel;
- the due-source integrity validator remains an independent check that every due source has exactly one matching route summary and Coverage row and that source, channel, and execution status reconcile;
- a route required by the due-source contract must not simultaneously be treated as an orphan by Worker Audit.

Historical manual checkpoints may explicitly opt into one narrow C1 broad-route compatibility bridge: `worker/c1/broad/0N` may be reconciled to persisted `worker/broad/N` only when the persisted route summary is uniquely identified and carries the exact `materialized_from_sealed_g2_journal` marker. Canonical and legacy identities appearing together fail closed. The bridge changes only the in-memory validation universe; it never edits the checkpoint rows.

Use the dedicated read-only validator for this case:

```text
python -m ails_intel.g3_checkpoint_validator \
  --date YYYY-MM-DD \
  --run-key AILS11M-... \
  --attempt AILS11M-...-A<n> \
  --allow-legacy-g2-route-aliases
```

`--allow-legacy-g2-route-aliases` is not a normal production relaxation. Omit it for current canonical attempts. Final Shadow acceptance exposes the same explicit switch so a controlled downstream continuation uses the identical route handoff at G3 and G8.

A failed or ambiguous handoff must stop at G3. Do not repair an earlier attempt in place merely to satisfy validation. Once the downstream contracts have been stabilized through checkpoint continuation, perform one clean end-to-end replay under the then-current canonical contracts for final certification.
