#!/usr/bin/env bash
# Reproducible Cloud Run deployment script following CDE (`cde-deploy-cloud-run`) standards.
set -euo pipefail

export PATH="$PATH:$HOME/google-cloud-sdk/bin:/usr/local/bin"

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || echo 'ryan-sandbox-agent')}"
if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  PROJECT="ryan-sandbox-agent"
fi
REGION="${REGION:-us-central1}"
DATASET_ID="${BQ_DATASET_ID:-thelook_ecommerce_agent}"
REPO="${REPO:-demo-eng-images}"
SERVICE="${SERVICE:-cymbal-agentic-bi-showcase}"
SA_NAME="${SA_NAME:-cymbal-bi-showcase-sa}"
SA_EMAIL="${SERVICE_ACCOUNT:-${SA_NAME}@${PROJECT}.iam.gserviceaccount.com}"

SHA_TAG="$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}:${SHA_TAG}"

# On Cloudtop where Application Default Credentials (ADC) are configured instead of GCE VM metadata
if ! gcloud projects describe "${PROJECT}" >/dev/null 2>&1; then
  ADC_TOKEN="$(gcloud auth application-default print-access-token 2>/dev/null || true)"
  if [[ -n "${ADC_TOKEN}" ]]; then
    export CLOUDSDK_AUTH_ACCESS_TOKEN="${ADC_TOKEN}"
  fi
fi

echo "==> [1/5] Verifying GCP project (${PROJECT}) & dedicated least-privilege Service Account (${SA_EMAIL})..."
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project "${PROJECT}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --project "${PROJECT}" \
    --display-name "Cymbal Agentic BI Showcase Cloud Run SA"
fi

for ROLE in \
  "roles/bigquery.user" \
  "roles/bigquery.dataViewer" \
  "roles/aiplatform.user" \
  "roles/geminidataanalytics.dataAgentUser"; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet >/dev/null
done

echo "==> [2/5] Ensuring Artifact Registry repository '${REPO}' in '${REGION}'..."
gcloud artifacts repositories create "${REPO}" \
  --project "${PROJECT}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Cloud Demo Engineering container images" 2>/dev/null || true

echo "==> [3/5] Building multi-stage container via Cloud Build (${IMAGE})..."
gcloud builds submit \
  --project "${PROJECT}" \
  --tag "${IMAGE}" \
  .

echo "==> [4/5] Deploying '${SERVICE}' to Cloud Run (${REGION})..."
gcloud run deploy "${SERVICE}" \
  --project "${PROJECT}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --service-account "${SA_EMAIL}" \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 5 \
  --timeout 240 \
  --session-affinity \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT},BQ_DATASET_ID=${DATASET_ID},GOOGLE_CLOUD_LOCATION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=TRUE" \
  --quiet

# Attempt public demo invoker policy if permitted by Org Policy (gracefully skipped under Argolis DRS)
gcloud run services add-iam-policy-binding "${SERVICE}" \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --quiet 2>/dev/null || echo "Note: Domain Restricted Sharing active; access via authenticated IAM or 'gcloud run services proxy'."

echo "==> [5/5] Verifying live service URL..."
URL="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
echo "${URL}"

ID_TOKEN="$(gcloud auth print-identity-token 2>/dev/null || true)"
if [[ -n "${ID_TOKEN}" ]]; then
  curl -fsS -H "Authorization: Bearer ${ID_TOKEN}" "${URL}/api/health" && echo ""
else
  curl -fsS "${URL}/api/health" && echo "" || true
fi
