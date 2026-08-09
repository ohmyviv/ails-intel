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

The collector runtime now supports generic RSS adapters configured entirely through private `structured_collectors_json` options. Feed URLs and relevance expressions are runtime configuration, not hard-coded collector behavior. This lets selected stable open feeds join the same deterministic Signal layer without turning dynamic/paywalled media into brittle public scrapers.

## Validation

`Unified Signal Ingestion Validation` performs public-safe checks only. It reports aggregate counts, a hash of the required route manifest, and compact error labels. It does not log private queries, raw titles, snippets, entity names, Candidate content, or report bodies.

The validator is intentionally stricter than the Sprint 3 transaction validators: a previously passed Shadow run can fail this new contract if its news/entity routes were not persisted at route level. This is expected for pre-Sprint-4 history and is not a reason to rewrite historical rows.
