# AILS Intel

Recall-aware AI life science intelligence system.

This public repository contains **execution and deployment code only**. Operational intelligence — source registries, entity watchlists, search plans, prompts, thresholds, runtime state, signals, candidates, and reports — is stored outside this repository.

## Security model

- No long-lived Google service-account key is stored in GitHub.
- Google access uses GitHub OIDC + Google Workload Identity Federation.
- Pull-request CI receives no production identity or secrets.
- Live workflows run from the default branch with least-privilege permissions.
- Logs contain operational status/counters only, never report bodies or private configuration.
- Runtime intelligence data is not uploaded as GitHub Actions artifacts.

## Status

Sprint 1.5: public-repository deployment hardening.

See `docs/deployment-public.md` for one-time Google Cloud and GitHub setup.
