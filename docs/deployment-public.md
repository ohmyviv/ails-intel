# Public GitHub Deployment

Target repository:

```text
ohmyviv/ails-intel
```

The repository is public so standard GitHub-hosted runners are free. The repository must contain code only; operational intelligence remains in the private Google Sheet.

## 1. Google Cloud prerequisites

You need a Google Cloud project you control, `gcloud` installed locally, and permission to create service accounts and Workload Identity Federation resources.

Set variables:

```bash
export PROJECT_ID="YOUR_GCP_PROJECT_ID"
export REPO="ohmyviv/ails-intel"
export POOL_ID="github-ails"
export PROVIDER_ID="github-ails"
export SA_NAME="ails-intel-actions"

gcloud config set project "$PROJECT_ID"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
```

Enable required APIs:

```bash
gcloud services enable \
  iamcredentials.googleapis.com \
  sheets.googleapis.com
```

Create the service account:

```bash
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="AILS Intel GitHub Actions"
```

The service account does not need broad Google Cloud project roles for direct Google Sheet file access. The target private Sheet will be shared directly with this account.

## 2. Create Workload Identity Federation

Create a dedicated pool:

```bash
gcloud iam workload-identity-pools create "$POOL_ID" \
  --location="global" \
  --display-name="GitHub AILS Intel"
```

Create a GitHub OIDC provider restricted to this repository and the `main` branch:

```bash
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --location="global" \
  --workload-identity-pool="$POOL_ID" \
  --display-name="GitHub AILS Intel" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref,attribute.actor=assertion.actor" \
  --attribute-condition="assertion.repository=='ohmyviv/ails-intel' && assertion.ref=='refs/heads/main'"
```

Allow only this repository identity to impersonate the service account:

```bash
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${REPO}"
```

Build the provider resource name:

```bash
export WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"
echo "$WIF_PROVIDER"
echo "$SA_EMAIL"
```

IAM/WIF changes can take several minutes to propagate.

## 3. Share the private Google Sheet

Share the production state workbook directly with the service-account email shown by:

```bash
echo "$SA_EMAIL"
```

Use **Editor** because later collectors and workers will write runtime state. Do not make the workbook public.

## 4. Configure GitHub

Repository **Variables**:

```text
GCP_PROJECT_ID                 = YOUR_GCP_PROJECT_ID
GCP_WORKLOAD_IDENTITY_PROVIDER = projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-ails/providers/github-ails
GCP_SERVICE_ACCOUNT            = ails-intel-actions@YOUR_GCP_PROJECT_ID.iam.gserviceaccount.com
```

Repository **Secret**:

```text
AILS_SPREADSHEET_ID = private workbook ID
```

Do not store any long-lived Google service-account JSON key in GitHub.

## 5. Repository security settings

Recommended:

1. Default branch: `main`.
2. After bootstrap, require pull requests before merging into `main`.
3. Require the CI status check.
4. Disable force pushes to `main`.
5. Keep default Actions workflow token permissions read-only.
6. Production workflows explicitly request only `contents: read` and `id-token: write`.
7. Never use `pull_request_target` for workflows with production identity.
8. Enable secret scanning and push protection where available.
9. Enable private vulnerability reporting where available.

## 6. First live tests

Run manually from GitHub Actions:

1. `CI`
2. `Live Schema Validation`
3. `Daily Report Watchdog`

The watchdog can legitimately fail when the expected business run is absent; distinguish that from authentication or schema failure.

Do not set `require_shadow=true` until the v11 shadow worker itself is running.

## 7. Public-log policy

Allowed in public Actions logs:

- component/stage/status;
- run key / attempt ID;
- collector/source IDs;
- counts;
- coverage confidence;
- elapsed time;
- fingerprints.

Forbidden:

- private Sheet values;
- candidate/report bodies;
- private search plans/prompts;
- private URLs;
- API response bodies;
- access/OIDC tokens;
- generated credential files.

## 8. No runtime artifacts

Do not upload Signals, Candidates, report Markdown, Sheet snapshots, auth files, or search responses as public GitHub Actions artifacts. The private Google Sheet/Drive remains the operational state store.
