# Public Repository Threat Model

## Assets kept private

- state workbook locator;
- source registry;
- monitored entities;
- exact search plans;
- prompts and reasoning contracts;
- signals/candidates/reports;
- runtime history;
- future API keys;
- Google identity tokens.

## Trust boundaries

### Pull requests and forks

Untrusted. CI has `contents: read` only and receives no OIDC production identity or repository secrets.

### Scheduled/manual workflows on `main`

Trusted only after branch protection/review. These workflows request `contents: read` and `id-token: write`; Google WIF additionally restricts admission to the intended repository and `refs/heads/main`.

### Google service account

Access is scoped primarily by direct sharing of the target Sheet. Avoid project-wide roles unless a later component explicitly requires them.

## Primary failure modes

1. Secret committed to Git history.
2. Private Sheet contents printed into public Actions logs.
3. Third-party Action supply-chain compromise.
4. Pull request gaining production OIDC permissions.
5. Over-broad WIF principal binding.
6. Runtime intelligence uploaded as a public artifact.

Mitigations: no long-lived key, SHA-pinned Actions, leak guard, allowlisted logs, WIF attribute restrictions, read-only PR permissions, and no runtime artifacts.
