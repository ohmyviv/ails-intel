# Sprint 4.6 — Recall & Provenance

Sprint 4.6 turns missed-event review into a deterministic feedback loop without weakening the existing Signal-first transaction boundary.

## Scope

Sprint 4.6 is split into four bounded increments:

- **4.6A — Challenger Audit + provenance contract.** External search/tool output is post-hoc audit input. It is classified and measured, but it is not a direct Candidate source.
- **4.6B — Hard Event Recall Expansion.** Improve recall for financing, licensing/BD, PCC/IND/first-patient milestones, regulatory decisions, commercial deployment, and regional business news.
- **4.6C — Event Atomization + Date Provenance.** Preserve the distinction between article publication, first public disclosure, event date, and system discovery; one article may describe multiple atomic events.
- **4.6D — Technical Recall + Entity Aliases.** Improve technical-query recall and multilingual/former-name entity matching.

Private search vocabulary, source locators, monitored entities, and operational challenger inputs remain in private runtime state and are not stored in this public repository.

## 4.6A invariant

The external challenger is an **audit lane, not an authority lane**.

```text
external challenger item
        ↓
primary-source chase + temporal/scope check
        ↓
challenger disposition
        ↓
miss accounting / regression input
```

It does **not** create a Candidate directly. If a confirmed miss is later allowed to affect a future report, it must be rediscovered or promoted through the normal auditable path and exist as an active same-run Signal before Candidate formation.

The six terminal challenger dispositions are:

- `confirmed_miss`
- `stale_resurfacing`
- `duplicate_known_event`
- `scope_mismatch`
- `evidence_insufficient`
- `false_or_inaccurate_claim`

Only `confirmed_miss` contributes to miss counts. A confirmed miss requires primary-source verification plus sufficient temporal provenance to show that the underlying event belonged to the audited reporting window. Existing miss type and severity taxonomies remain authoritative for `discovery_miss`, `verification_miss`, `selection_miss`, `timing_miss` and `critical`, `material`, `minor`.

## Time provenance

Do not collapse these meanings:

- `source_published_at`: when the article/source page was published.
- `first_public_at`: earliest verified public disclosure of the atomic event.
- `event_date`: when the underlying event occurred, when known.
- `received_at_bjt` / system discovery time: when the challenger or collector observed the item.

A newly published article describing an older event is not automatically a new Hard Event.

## 4.6A public contract

`ails_intel.challenger_audit` provides deterministic challenger IDs, item-level validation, duplicate detection, confirmed-miss summaries, reporting-window checks, and reconciliation against run-level miss counters.

The intended private persistence table is `Lite_ChallengerAudit`. Its row contract is exposed by `CHALLENGER_HEADERS`; private runtime deployment and live readback are separate acceptance steps and must not be inferred from unit-test success.

## Acceptance

Code/CI acceptance requires deterministic ID behavior, no duplicate challenger IDs in one audit snapshot, strict terminal disposition validation, primary-source and time-provenance requirements for confirmed misses, and exact reconciliation of item-level confirmed/critical/material misses to the run counters.

Live acceptance additionally requires the private audit table/config to be deployed and read back successfully, followed by a real challenger audit. Until that happens, Sprint 4.6A is code-complete at most, not live-proven.
