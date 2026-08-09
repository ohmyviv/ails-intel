# Sprint 2 — Deterministic Structured Collectors

Sprint 2 moves structured, date-windowed discovery out of the reasoning worker and into deterministic GitHub Actions code.

## Enabled collectors

Runtime enablement and source IDs are read from the private `Lite_Config` and `SourceRegistry` tables.

The public engine currently implements adapters for:

- PubMed / NCBI E-utilities
- arXiv API
- bioRxiv API
- medRxiv via the bioRxiv API service
- ClinicalTrials.gov API v2

Exact watch terms and source queries remain in the private Sheet. The public repository does not contain the operational query vocabulary.

## State contract

Collectors write only:

- `Lite_Signals`
- collector-owned rows in `Lite_SourceCoverage`

They do not write:

- `Lite_Runs`
- `Lite_Candidates`
- `Lite_DailyItems`
- `Lite_EventIndex`

Signals are exact-deduped by `run_key + signal_key`. `signal_key` is SHA-256 over source ID, stable ID/canonical URL, normalized title, and publication date.

Collector SourceCoverage rows are deterministic upserts keyed by `coverage_id`.

## Shadow safety

Current runtime configuration is `execution_mode=shadow`, so the generated run key uses the `AILS11S-...` namespace. The same code can use the production prefix only after the private config is explicitly cut over.

## Completion and saturation

`execution_status` and `saturation_status` are separate.

- `complete`: the configured bounded query/window was fully enumerated.
- `partial`: a configured result cap prevented full enumeration.
- `failed`: the API call/parse pipeline failed.
- `saturated`: there were more results than the configured output/scan capacity.

A saturated route is not silently described as complete.

## Public logging

Logs contain only collector/source IDs, run key, execution status, saturation status, counts, batch ID, and elapsed time. Query strings, response bodies, titles, abstracts, URLs, and Sheet contents are never logged.

## Initial cadence

The first live cadence is intentionally conservative:

- 19:47 Asia/Shanghai daily: all structured collectors
- manual `workflow_dispatch`: all collectors or one selected collector

Multiple intraday collection passes will be added only after observing API volume, saturation, and runtime in shadow mode.
