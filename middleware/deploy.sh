#!/usr/bin/env bash
# Deploy the Flask middleware to Cloud Run.
# Usage:  bash deploy.sh
# Prereq: gcloud auth login && gcloud config set project finial-project-494209

set -euo pipefail

PROJECT_ID="finial-project-494209"
REGION="europe-west6"
SERVICE="weather-flask"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"

echo "▶ Building and pushing container image..."
gcloud builds submit --tag "${IMAGE}" .

echo "▶ Deploying to Cloud Run (${REGION})..."
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=${PROJECT_ID},\
BQ_DATASET=Lab4_IoT_datasets,\
BQ_TABLE=weather-records,\
OWM_API_KEY=${OWM_API_KEY:?Set OWM_API_KEY in your shell},\
OWM_CITY=${OWM_CITY:-Lausanne},\
OWM_COUNTRY=${OWM_COUNTRY:-CH},\
DEVICE_PASSWD=${DEVICE_PASSWD:?Set DEVICE_PASSWD in your shell}"

echo "✅ Deployment complete."
gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --format "value(status.url)"
