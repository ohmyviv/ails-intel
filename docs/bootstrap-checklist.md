# Bootstrap Checklist

## Public repository

- [ ] Repository is `ohmyviv/ails-intel` and public.
- [ ] ChatGPT GitHub connector/app has access to the new repository if automated commits are desired.
- [ ] Initial Sprint 1.5 code is committed.
- [ ] CI passes.
- [ ] No OSS license is present unless intentionally added later.

## Google Cloud

- [ ] A dedicated/appropriate Google Cloud project is selected.
- [ ] WIF pool/provider created.
- [ ] Provider condition restricts repository to `ohmyviv/ails-intel`.
- [ ] Provider condition restricts ref to `refs/heads/main`.
- [ ] Service account created.
- [ ] `roles/iam.workloadIdentityUser` binding created only for this repository identity.
- [ ] Private state Sheet shared with service account as Editor.

## GitHub configuration

- [ ] Variable `GCP_PROJECT_ID` set.
- [ ] Variable `GCP_WORKLOAD_IDENTITY_PROVIDER` set.
- [ ] Variable `GCP_SERVICE_ACCOUNT` set.
- [ ] Secret `AILS_SPREADSHEET_ID` set.
- [ ] Default Actions token permission is read-only.
- [ ] Branch protection configured after bootstrap.
- [ ] Secret scanning/push protection enabled where available.

## Live verification

- [ ] `Live Schema Validation` succeeds manually.
- [ ] `Daily Report Watchdog` authenticates successfully.
- [ ] Watchdog business result is interpreted separately from auth result.
- [ ] `require_shadow` remains off until v11 shadow worker exists.

## Sprint 2 readiness

- [ ] No long-lived Google key exists in repository or Actions settings.
- [ ] Public leak guard passes.
- [ ] No runtime data artifacts are uploaded.
- [ ] Sprint 1.5 acceptance review complete.
