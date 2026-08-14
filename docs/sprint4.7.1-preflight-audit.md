# v11 Corrective Sprint 4.7.1 — Acceptance Preflight Audit

Date: 2026-08-14 (BJT)

## Scope

This is a read-only preflight for the next v11 Shadow operational acceptance. It does not create a Shadow run, write Coverage/Signals/Candidates/DailyItems, change the 20:30 schedule, or rewrite the frozen 2026-08-14 incident.

The audit intentionally separates:

- rollout/configuration readiness;
- executable semantic consistency;
- post-run operational evidence;
- natural scheduled acceptance.

## Result

**Preflight status: PASS after one non-behavioral residue cleanup in the acceptance-pack PR.**

The live private configuration and the 20:30 runtime instructions are aligned with the 4.7.1 architecture rule:

> Fail closed on integrity; degrade gracefully on coverage.

### Snapshot Barrier

- Snapshot Barrier is enabled.
- The observation set is all enabled structured collectors, not only legacy `barrier_required` sources.
- The current config contains 10 enabled structured collectors.
- The configured same-day freshness clock is 18:00 BJT.
- `complete`, `partial`, `failed`, and `skipped` are terminal observations.
- Missing, duplicate/inconsistent, stale, malformed, or non-terminal observations remain fail-closed.
- Freeze-time Signal snapshot recheck is enabled.

### Worker / Unified Ingestion

- Worker Signal ingestion is required before Candidate formation.
- Candidate source Signal references must resolve to active same-run Signals.
- Required Worker routes must persist route-level Coverage even on no-hit.
- Worker Audit is enabled and required before pass.
- All plan IDs currently mapped by the Worker channel plan map resolve to active private SearchPlans entries.
- The three Sprint 4.6B.1 hard-event recall routes are active: `V11-HR-FIN`, `V11-HR-DEV`, and `V11-HR-REGCOM`.

### Coverage / Rescue / Freeze

- Coverage Gate remains enabled and still classifies HIGH/MEDIUM/LOW using the current channel model.
- Rescue is enabled.
- LOW is a coverage-quality result, not a transaction-integrity veto.
- LOW pre-Rescue still requires the configured bounded Rescue path.
- Freeze/readback remains fail-closed on selected-item, manifest, fingerprint, ownership, and readback integrity.

### Runtime / handoff consistency

The active 20:30 runtime instruction and the Canonical Handoff both contain the Corrective Sprint 4.7.1 precedence rule. Historical wording from earlier sprints remains audit history and is not treated as current executable policy.

## Old-semantics residue scan

Executable source was reviewed for retired single-source-veto semantics and retired LOW-coverage veto tokens.

One real residue was found: `unified_ingestion.py` still contained a duplicate, old implementation of Snapshot Barrier that classified `failed`/`skipped` collectors as unready. The live unified-ingestion CLI already imported the corrected implementation from `snapshot_policy.py`, so this duplicate was not the current live path, but it was an importable future hazard.

The acceptance-pack PR removes that duplicate and makes `snapshot_policy.py` the single executable owner of Snapshot Barrier semantics. A static regression test now enforces:

- only `snapshot_policy.py` defines `validate_structured_snapshot_barrier`;
- retired `structured_snapshot_unready_collector` is absent from executable source;
- retired `freeze_not_allowed_from_low_coverage` is absent from executable source;
- retired `final_coverage_still_low` is absent from executable source.

Legacy names such as `barrier_required` may remain in compatibility APIs, historical docs, or private notes, but they must not restore source-level veto behavior.

## What this preflight does not prove

This preflight does **not** prove that a natural 20:30 Shadow will execute Worker routes, persist audit rows, reach Freeze, archive correctly, or continue after a real collector failure. Those are operational facts and must be established by the post-run acceptance process.
