# Terraform Infrastructure (`click-to-deploy/`)

This directory provisions the Google Cloud infrastructure for **Cymbal Agentic BI Showcase**:

- Enables required APIs (`bigquery`, `geminidataanalytics`, `aiplatform`, `dataplex`, `cloudtrace`, `run`, `artifactregistry`, `cloudbuild`)
- Creates Artifact Registry Docker repository (`demo-eng-images`)
- Creates BigQuery dataset (`cymbal_enterprise_dw`)
- Creates dedicated least-privilege runtime service account (`cymbal-bi-showcase-sa`) with project-level `roles/bigquery.user` and `roles/aiplatform.user`, plus dataset-level `roles/bigquery.dataViewer`
- Deploys the Cloud Run service (`cymbal-agentic-bi-showcase`) with `session_affinity = true`, `2 vCPU / 2 GiB`, and `600s` timeout

> For single-command shell deployment (Cloud Build + IAM + Cloud Run), you can also run `./scripts/deploy.sh` from the repository root.

---

## Step-by-Step Deployment

### 1. Authenticate & Set Project

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"

gcloud auth login
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform"
gcloud config set project "${PROJECT_ID}"
```

### 2. Build & Push Container Image

Initialize Terraform, create the Artifact Registry repository first (or import it if `./scripts/deploy.sh` already created it), and push the container image:

```bash
terraform -chdir=click-to-deploy init

terraform -chdir=click-to-deploy apply \
  -target=google_project_service.apis \
  -target=google_artifact_registry_repository.images \
  -var="project_id=${PROJECT_ID}"

SHA_TAG="$(git rev-parse --short HEAD)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/demo-eng-images/cymbal-agentic-bi-showcase:${SHA_TAG}"
LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/demo-eng-images/cymbal-agentic-bi-showcase:latest"

gcloud builds submit --project "${PROJECT_ID}" --tag "${IMAGE}" .
gcloud artifacts docker tags add "${IMAGE}" "${LATEST}" --quiet
```

*(If `demo-eng-images` already exists in `${PROJECT_ID}`, import it once before `apply`: `terraform -chdir=click-to-deploy import -var="project_id=${PROJECT_ID}" google_artifact_registry_repository.images projects/${PROJECT_ID}/locations/${REGION}/repositories/demo-eng-images`.)*

### 3. Provision Warehouse Tables, Seed Data & 7 BigQuery Data Agents

Terraform creates an empty BigQuery dataset; the Python provisioning scripts populate the 32 documented tables (`thelook_ecommerce` 7 + `tpc_ds_1g` 25), seed relative-timestamp scenario rows, and upsert the 7 Conversational Analytics data agents (`1` warehouse-wide + `6` domain-scoped):

```bash
export GOOGLE_CLOUD_PROJECT="${PROJECT_ID}"
export GOOGLE_CLOUD_LOCATION="${REGION}"
export GOOGLE_GENAI_USE_VERTEXAI=TRUE

uv sync
uv run python scripts/provision_enterprise_warehouse.py
uv run python scripts/refresh_demo_seed.py
uv run python scripts/provision_cymbal_caa_agents.py
```

### 4. Apply Full Terraform Stack & Grant Per-Agent Runtime Access

```bash
terraform -chdir=click-to-deploy apply \
  -var="project_id=${PROJECT_ID}" \
  -var="container_image=${IMAGE}"
```

Then bind `roles/geminidataanalytics.dataAgentUser` on the 7 demo data agents to the Cloud Run service account:

```bash
python3 scripts/grant_runtime_access.py \
  --service-account "cymbal-bi-showcase-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project "${PROJECT_ID}" \
  --dataset "cymbal_enterprise_dw"
```

---

## Ingress & Organization Policy Options

- **Default (`allow_unauthenticated = false`, `ingress = "INGRESS_TRAFFIC_ALL"`)**: Safe for organizations enforcing Domain Restricted Sharing (`constraints/iam.allowedPolicyMemberDomains`). Open the service locally via authenticated proxy:
  ```bash
  gcloud run services proxy cymbal-agentic-bi-showcase --region "${REGION}" --project "${PROJECT_ID}" --port 8080
  ```
- **Public Demo URL**: Pass `-var="allow_unauthenticated=true"` if your project permits `allUsers` invokers.
- **Internal / Load Balancer Only (`constraints/run.allowedIngress`)**: Pass `-var="ingress=INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"` when fronting Cloud Run with an External Application Load Balancer + Serverless NEG + Identity-Aware Proxy.

---

## Teardown

```bash
terraform -chdir=click-to-deploy destroy -var="project_id=${PROJECT_ID}"
```
