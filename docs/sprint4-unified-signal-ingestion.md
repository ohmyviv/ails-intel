# Sprint 4 — Unified Signal Ingestion

Sprint 4 closes the discovery-path asymmetry between deterministic collectors and the ChatGPT reasoning worker.

## Invariant

Every discovery clue that can influence a v11 Candidate must first exist as an active `Lite_Signals` row for the same `run_key`. A Candidate may not be created directly from an ephemeral web result.

The unified path is:

`source/API/web/entity check -> Lite_Signals -> event clustering -> Lite_Candidates -> Coverage Gate -> Freeze`

## Worker-discovered Signals

Web, premium-media, entity, regulator, company, product/deployment, regional and rescue discoveries use:

- `producer_id = chatgpt/worker` or `chatgpt/rescue`
- `origin_attempt_id = <fully-qualified shadow attempt>`
- an explicit `channel_id` and `route_id`
- a concrete title and URL
- deterministic `signal_key` and `signal_id`
- `signal_state = active`
- `schema_version = v11.0`

Private query text and private entity metadata remain in the private Sheet and must not be written to public logs or artifacts.

## Route-level Coverage

A channel-level `complete` claim must be backed by route-level `Lite_SourceCoverage` rows. Route IDs are deterministic and contain identifiers, not private query text.

Key route families:

- mapped SearchPlan: `worker/plan/<plan_id>`
- C1 broad search slot: `worker/c1/broad/<NN>`
- named source check: `worker/source/<source_id>`
- independent P0 entity check: `worker/entity/<entity_id>`

A route with a hit must have at least one active worker Signal on that same attempt/channel/route. A worker Signal must also have a matching coverage route.

## Candidate referential integrity

`Lite_Candidates.source_signal_ids` remains mandatory. The unified-ingestion validator rejects any Candidate that references a non-active or foreign-run Signal.

## Deterministic news sensors

The collector runtime supports generic RSS adapters configured entirely through private `structured_collectors_json` options. Feed URLs and relevance expressions are runtime configuration, not hard-coded collector behavior. This lets selected stable open feeds join the same deterministic Signal layer without turning dynamic/paywalled media into brittle public scrapers.

## Sprint 4.2 — Collector snapshot barrier

GitHub cron time is a scheduling target, not a transaction boundary. A scheduled collector can start late enough to overlap the reasoning worker. The Worker must therefore never assume that the expected cron time means the structured snapshot is final.

The snapshot barrier requires:

- every enabled structured collector has exactly one same-run `Lite_SourceCoverage` row;
- its persisted `checked_at_bjt` is on the report date and not earlier than the configured barrier time;
- a collector may be `complete` or `partial` at the barrier, while `failed`, `skipped`, missing, or stale rows are not safe inputs;
- the reasoning worker freshly re-reads active Signals after the barrier, rather than reusing state read at task startup or during the production phase;
- a post-run validator compares the run's declared `signal_count` with the current active same-run Signal count and reports `signal_count_snapshot_drift` when new Signals appeared after the consumed snapshot.

The scheduled collector target is moved earlier to provide operational margin, but the barrier remains authoritative. Moving cron earlier is not considered a correctness mechanism by itself.

If drift is detected before Freeze, the Worker must refresh discovery/Candidate formation. If drift is detected after Freeze, frozen content must not be silently rewritten; the Shadow attempt must remain non-passed until the discrepancy is handled according to the state machine.

## Validation

`Unified Signal Ingestion Validation` performs public-safe checks only. It reports aggregate counts, a hash of the required route manifest, and compact error labels. It does not log private queries, raw titles, snippets, entity names, Candidate content, or report bodies.

The validator is intentionally stricter than the Sprint 3 transaction validators: a previously passed Shadow run can fail this contract if its news/entity routes were not persisted at route level or if its structured Signal snapshot drifted after reasoning. This is expected for diagnostic Shadow history and is not a reason to rewrite historical rows.
