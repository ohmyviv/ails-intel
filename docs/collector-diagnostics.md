# Collector Diagnostics

`Collector Diagnostics` is a read-only GitHub Actions workflow for checking structured-source health without writing Signals or SourceCoverage rows.

## Default automated diagnostic set

When no collector input is supplied, the runner checks:

- `COL-HITNEWS-AI`
- `COL-BIORXIV`
- `COL-MEDRXIV`
- `COL-FIERCE-RSS`
- `COL-PUBMED`

A manual `workflow_dispatch` may pass one collector ID, comma-separated IDs, or `all`.

## ChatGPT automation path

The workflow checks out `ref: main` explicitly. This means an Actions job re-run executes the latest `main` code and reads the latest live configuration even though GitHub associates the re-run with the original workflow run.

The workflow uses the read-only Google Sheets OAuth scope and the diagnostic runner never calls Signal or Coverage write methods. Source failures are logged as `DEGRADED` evidence and do not fail the workflow; configuration or invocation errors do fail it.

The workflow also runs automatically when its workflow file or diagnostic runner is first changed on `main`, providing a bootstrap run that can subsequently be re-run through the GitHub Actions API.
