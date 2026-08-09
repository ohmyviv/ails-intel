# Security Policy

Do not open a public issue containing credentials, tokens, private URLs, Google
Sheet contents, report bodies, candidate data, or operational intelligence.

If you believe a secret or private operational value has been exposed:

1. Revoke or rotate the affected credential immediately.
2. Remove the value from the current branch.
3. Treat Git history and Actions logs as compromised until verified clean.
4. Use GitHub private vulnerability reporting/security advisory features when available.

Production Google access is designed around short-lived GitHub OIDC federation,
not long-lived service-account keys.
