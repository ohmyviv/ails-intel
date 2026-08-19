# G2 Worker Execution-Fact Journal

This contract closes the gap between a Worker tool execution and the later `Lite_WorkerAudit` route summary. The problem class is a syntactically valid, internally consistent summary whose numeric counts do not match what the Worker actually executed.

The journal is private execution-local state. It MUST NOT contain private query text in public GitHub logs, issues, Actions artifacts, or report output.

## Boundary

The execution chain is:

`tool execution -> append-only execution event -> fsync/readback -> deterministic route summary -> Lite_WorkerAudit -> Worker Signals -> Lite_SourceCoverage`

The five route execution counts are facts derived from events, not values authored from memory:

- `results_returned`: exact concrete result-card count on `search_returned`
- `results_screened`: count of unique `result_screened` events
- `pages_opened`: count of successful unique `page_opened` events
- `fresh_results`: screened events with `fresh=true`
- `qualifying_results`: screened events with `disposition=qualified_signal`

A `route_finalized` event is forbidden from supplying any of those count fields.

## Required lifecycle

Each required logical route is isolated and must be fully sealed before another route starts:

1. `route_started`
2. exactly one of `search_returned` or `search_failed`
3. zero or more `page_opened` / `result_screened` events
4. `route_finalized`
5. `route_sealed`

After every tool response that changes execution facts, the corresponding event must be durably appended and read back before another Worker search/listing/open call occurs. In particular, `search_returned` must be journalled before the first `page_opened`. This is an execution-order contract, not a best-effort reconstruction rule.

The implementation uses a global append sequence plus a SHA-256 previous-event hash chain. Historical events have no update API.

## Failure semantics

Validation fails closed on missing routes, orphan routes, event-order violations, route interleaving, sequence/hash defects, duplicate search terminals, duplicate screened/opened result ranks, invalid result ranks, unsealed routes, or any route summary that differs from the event-derived facts.

A successful true-zero route is derived from `search_returned(results_returned=0)` followed by `route_finalized(execution_status=complete)` and `route_sealed`, with no screen/open events.

A search/tool/access failure uses `search_failed` and a `partial` or `failed` final status. Numeric counts may still derive to zero, but the route is not a successful true-zero.

If the execution journal is incomplete or inconsistent, G2 fails and G3 must not begin. Recovery starts a new attempt and reruns all required Worker routes; missing execution events are never reconstructed from chat memory.

## G3 materialization

`Lite_WorkerAudit` route summaries must be created with `materialize_route_summary()` from a sealed route event stream. Callers may provide non-execution metadata such as `run_key`, `attempt_id`, `producer_id`, source/query references and schema version, but cannot override `execution_status` or any of the five execution counts.

Before Candidate formation, G3 still performs the existing Audit -> Signal -> Coverage reconciliation. The execution journal adds the missing upstream proof that the Audit counts correspond to actual Worker execution.

## Regression coverage

The tests cover:

- exact `pages_opened` mismatch detection, including the 2026-08-18 failure class
- `page_opened` before journalled `search_returned`
- starting the next route before the previous route is sealed
- successful true zero versus failed search
- the ENT-001 exact-one result regression
- manual count injection into `route_finalized`
- hash-chain tampering
- materialization before route sealing
