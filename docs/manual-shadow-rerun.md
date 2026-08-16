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
