#!/usr/bin/env bash
# Cleanly tears down Cloud Run demo resources to prevent ongoing cloud cost.
set -euo pipefail

export PATH="$PATH:$HOME/google-cloud-sdk/bin:/usr/local/bin"

PROJECT="${PROJECT:-ryan-sandbox-agent}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-cymbal-agentic-bi-showcase}"

if ! gcloud projects describe "${PROJECT}" >/dev/null 2>&1; then
  ADC_TOKEN="$(gcloud auth application-default print-access-token 2>/dev/null || true)"
  if [[ -n "${ADC_TOKEN}" ]]; then
    export CLOUDSDK_AUTH_ACCESS_TOKEN="${ADC_TOKEN}"
  fi
fi

echo "Deleting Cloud Run service '${SERVICE}' in ${PROJECT} (${REGION})..."
gcloud run services delete "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --quiet || true
echo "Teardown complete."
