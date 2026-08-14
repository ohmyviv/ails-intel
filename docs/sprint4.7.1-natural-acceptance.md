# v11 Corrective Sprint 4.7.1 — Natural Acceptance Checklist

This checklist is frozen before the first prospective natural run on or after 2026-08-15. It must not be relaxed after seeing run results.

## Acceptance evidence classes

Keep these labels separate:

- **Code/CI PASS**: public contracts and tests passed.
- **Preflight PASS**: active configuration and executable semantics were read-only audited.
- **Manual regression PASS**: a manually initiated Shadow attempt passed the same ledger checks. This is useful regression evidence but cannot substitute for scheduled natural acceptance.
- **Natural baseline PASS**: a scheduled 20:30 Shadow passes all ledger and archive checks when no structured source failure occurs.
- **Natural source-failure path PASS**: a scheduled 20:30 Shadow contains at least one fresh terminal `failed`/`skipped` structured collector and still proves Worker continuation plus all downstream contracts.

If all collectors are healthy, the failure path is **NOT_EXERCISED**, not PASS and not FAIL.

## Frozen checklist

### A. Run identity and final state

- Exactly one selected attempt row exists for the evaluated `run_key + attempt_id`.
- `report_date` matches the target date.
- `transaction_id == attempt_id`.
- `canonical_attempt` is blank.
- Schema is v11.
- For an accepted completed Shadow: `stage=completed`, `final_status=shadow_passed`, `state_status=passed`, `delivery_status=delivered`, `resume_stage=passed`.
- `write_status` is successful and `readback_match=TRUE`.

### B. Snapshot Barrier integrity

- Observation set equals **all enabled structured collectors**.
- Every enabled collector has exactly one same-run fresh collector-level Coverage row at/after the configured freshness clock.
- `complete`, `partial`, `failed`, and `skipped` all satisfy terminal-observation integrity.
- Missing, duplicate, stale, malformed, or non-terminal collector observation fails acceptance.
- Current active same-run Signal count equals final accepted `Run.signal_count`; mismatch is snapshot drift and fails acceptance.

### C. Source-failure continuation

For policy-effective natural runs (2026-08-15 onward):

- If no collector is `failed/skipped`: mark `source_failure_path=NOT_EXERCISED`.
- If one or more collectors are `failed/skipped`: same-attempt Worker/Rescue Coverage must exist and downstream validation must continue.
- `failed/skipped + zero Worker/Rescue continuation` is `SOURCE_FAILURE_WITHOUT_WORKER_CONTINUATION` and fails acceptance.
- A manual 2026-08-14 regression attempt may explicitly force this check with the validator flag; it remains manual evidence only.

### D. Worker routes, Worker Audit, and Unified Signal Ingestion

- Required routes are derived from current active configuration, not from a frozen list in this document.
- Every required route has route-level same-attempt Coverage.
- Every required route has exactly one same-attempt Worker Audit `route_summary`.
- Audit `results_screened` reconciles to Coverage `results_seen`.
- Representative audit rows satisfy the configured bounded count contract.
- Audit qualifying-result counts reconcile to active same-attempt Worker/Rescue Signals.
- Every Worker Signal has a matching route Coverage row.
- Every Candidate `source_signal_ids` reference resolves to an active same-run Signal.
- `Run.candidate_count` and `Run.verified_count` reconcile to the durable Candidate set used for acceptance.

### E. Coverage and Rescue

- `coverage_confidence_pre_rescue` and final `coverage_confidence` are valid HIGH/MEDIUM/LOW values.
- If pre-Rescue coverage is LOW, bounded Rescue must have been triggered.
- Final LOW is **not** itself an acceptance failure.
- Coverage limitations and collector degradation must remain visible; they cannot be silently upgraded.

### F. Frozen Manifest and ownership

- Frozen DailyItems belong to the evaluated run/attempt and have contiguous `item_index=1..N`.
- Title and primary URL are present.
- `event_key_v11` and `delta_key` are non-empty and unique.
- Every Frozen Item maps to a selected Candidate with matching event/delta identity.
- Selected Candidate count, `selected_count`, and `frozen_item_count` reconcile.
- Frozen fingerprint recomputes exactly from the durable manifest.
- Formal `Lite_EventIndex` contains zero ownership/write for the Shadow run.

### G. Archive/readback

The public ledger validator intentionally does not read the private archived Google Doc body. Full acceptance therefore additionally requires a separate private archive readback confirming the configured Shadow marker, date, run/attempt identity, coverage, Frozen count, all Frozen titles/primary URLs, and archive parent.

A green ledger validator without this archive-body readback is **ledger PASS, archive EXTERNAL_REQUIRED**, not full natural acceptance.

## Post-run validator

Read-only CLI:

```bash
python -m ails_intel.shadow_acceptance_validator --date YYYY-MM-DD
```

For a specific attempt:

```bash
python -m ails_intel.shadow_acceptance_validator --date YYYY-MM-DD --attempt <qualified-attempt-id>
```

For a pre-effective-date manual regression that should enforce the source-failure continuation invariant:

```bash
python -m ails_intel.shadow_acceptance_validator --date YYYY-MM-DD --attempt <qualified-attempt-id> --enforce-continuation
```

A workflow-dispatch-only GitHub Action wraps this validator. It has **no schedule** and is not connected to the 20:30 runtime, so preparing it does not change natural-run behavior.

## Decision rule after the run

- Ledger validator FAIL → operational acceptance FAIL; investigate exact invariant before any architecture expansion.
- Ledger validator PASS + archive readback FAIL/not done → acceptance not complete.
- Ledger validator PASS + archive readback PASS + scheduled natural run → Natural baseline PASS.
- If that same natural run contains a failed/skipped collector and `source_failure_path=PASS` → Natural source-failure path PASS.
- If the natural run has no source failure → retain `source_failure_path=NOT_EXERCISED`; do not invent fault-path evidence.
