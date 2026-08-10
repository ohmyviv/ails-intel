# Sprint 4.4A — AI-Life-Science Specialist Sensors

## Objective

Increase deterministic discovery of AI-life-science industry events without turning the collector layer into a broad media crawler.

The first wave only enables specialist feeds that expose stable machine-readable endpoints. A high-value source without a stable feed remains a Worker route rather than being scraped with a brittle HTML parser.

## First-wave policy

- Specialist topic feeds are additive sensors, not replacements for C1/C4 Worker discovery.
- Feed URLs and private relevance expressions stay in private runtime configuration.
- Public code only implements generic RSS/Atom parsing and safe execution semantics.
- A healthy topic feed with no material event is `complete/no_hit`.
- Empty, stale, or unparsable feeds are `partial` or `failed`; they must not masquerade as healthy no-hit routes.
- Any relevant item becomes a same-run `Lite_Signal` before it can influence a Candidate.
- Existing run-key + signal-key idempotency and SourceCoverage reconciliation rules remain unchanged.

## Initial sources

### The Scientist — Artificial Intelligence

The publisher exposes an official Artificial Intelligence Atom feed. It is used as a specialist AI × life-science discovery sensor. Runtime relevance filtering remains event-oriented so general explainers do not automatically become hard-event Signals.

### Healthcare IT News — Artificial Intelligence

The publisher exposes its Artificial Intelligence topic in a machine-readable RSS mode. It is used primarily for clinical workflow, provider adoption, hospital deployment, governance, and product-use events.

### Endpoints News — AI channel

Endpoints' AI channel is retained as a high-priority Worker source. Sprint 4.4A does not introduce an HTML scraper because no stable official RSS/Atom endpoint was verified during implementation and the public channel can be access-controlled. This is intentional: deterministic coverage should fail closed rather than depend on a brittle anti-bot-sensitive parser.

## Acceptance criteria

For each enabled deterministic specialist feed:

1. The configured endpoint is fetched by the scheduled Structured Collectors workflow.
2. XML/Atom parsing returns a non-negative `parsed_count` and a safe `latest_published_date` diagnostic.
3. Window filtering and private relevance filtering execute without leaking private query text.
4. Coverage is persisted even on no-hit.
5. Relevant items are written as active same-run Signals with deterministic signal keys.
6. Re-running the same run key does not duplicate Signals or Coverage rows.
7. Collector execution does not write Runs, Candidates, DailyItems, or EventIndex.

## Non-goal

Sprint 4.4A does not try to maximize the number of media feeds. Sensor retention should later be based on unique event contribution, Candidate conversion, selected-item contribution, and failure rate.