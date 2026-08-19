# Frozen Structured source in final Shadow acceptance

A downstream-only manual Shadow continuation may reach final ledger acceptance without rerunning Structured Collectors or copying their persisted rows into the manual namespace.

## Contract

1. The source must be an immutable same-date scheduled Shadow (`AILS11S-*`) with an explicitly qualified source attempt.
2. Legacy pre-attempt-provenance source rows are first qualified by `legacy_frozen_replay` using their persisted fingerprint. Historical rows remain unchanged.
3. The qualified Structured fingerprint is verified again before final acceptance.
4. Only for read-only acceptance evaluation, collector Signal/Coverage copies are projected in memory into the `AILS11M-*` namespace. This makes the existing Snapshot Barrier and unified-ingestion checks evaluate one coherent manual snapshot without persisting cloned rows.
5. Current-run Worker/Rescue rows remain the durable A3/A<n> rows. If the manual namespace already contains persisted collector rows, the frozen-input projection fails closed rather than mixing two Structured inputs.
6. The final Worker route universe still comes from the sealed G2 -> G3 handoff, including due-source extensions and any explicitly enabled historical sealed-G2 broad-route compatibility bridge.
7. The archive-body readback contract remains external to the ledger validator and must pass before the Run is considered fully accepted.

## Validator

For a legacy Frozen Structured source:

```text
python -m ails_intel.frozen_shadow_acceptance_validator \
  --date YYYY-MM-DD \
  --run-key AILS11M-... \
  --attempt AILS11M-...-A<n> \
  --source-run-key AILS11S-... \
  --source-attempt AILS11S-...-A<n> \
  --source-persisted-fingerprint sha256:... \
  --allow-legacy-g2-route-aliases
```

The validator is read-only. It does not rerun discovery, does not create collector rows in the manual namespace, does not alter the scheduled source snapshot, and does not write EventIndex or canonical state.
