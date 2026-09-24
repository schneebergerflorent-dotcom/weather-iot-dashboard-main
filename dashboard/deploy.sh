#!/usr/bin/env bash
# Deploy the Streamlit dashboard to Cloud Run.
# Usage:  bash deploy.sh
# Prereq: gcloud auth login && gcloud config set project finial-project-494209

set -euo pipefail

PROJECT_ID="finial-project-494209"
REGION="europe-west6"
SERVICE="weather-dashboard"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"

MIDDLEWARE_URL="${API_BASE_URL:-https://weather-flask-297113273467.europe-west6.run.app}"

# ── Ensure background photo is present for Docker build ───────────────────────
PHOTO_DST="static/lausanne.jpg"
if [ ! -f "${PHOTO_DST}" ]; then
  PHOTO_SRC=$(find ../images -maxdepth 1 -iname "*.jpg" -o -iname "*.jpeg" | head -1)
  if [ -n "${PHOTO_SRC}" ]; then
    echo "▶ Copying background photo: ${PHOTO_SRC}"
    mkdir -p static
    cp "${PHOTO_SRC}" "${PHOTO_DST}"
  else
    echo "⚠️  No background photo found in ../images — panel will show gradient only."
  fi
fi

echo "▶ Building and pushing container image..."
gcloud builds submit --tag "${IMAGE}" .

echo "▶ Deploying to Cloud Run (${REGION})..."
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "API_BASE_URL=${MIDDLEWARE_URL}"

echo "✅ Dashboard deployed."
gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --format "value(status.url)"
