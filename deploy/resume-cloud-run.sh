#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${PROJECT:-gen-lang-client-0384080704}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-notatnik-adk-slice}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"
SMOKE="${SMOKE:-1}"
GCLOUD="${GCLOUD:-}"

if [[ -z "$GCLOUD" ]]; then
  if command -v gcloud >/dev/null 2>&1; then
    GCLOUD="gcloud"
  elif [[ -x "$HOME/google-cloud-sdk/bin/gcloud" ]]; then
    GCLOUD="$HOME/google-cloud-sdk/bin/gcloud"
  fi
fi

if [[ -z "$GCLOUD" ]] || ! command -v "$GCLOUD" >/dev/null 2>&1; then
  echo "gcloud not found. Set GCLOUD=/path/to/gcloud or install the Google Cloud CLI." >&2
  exit 127
fi

echo "Resuming public access for Cloud Run service:"
echo "  project:       $PROJECT"
echo "  region:        $REGION"
echo "  service:       $SERVICE"
echo "  max instances: $MAX_INSTANCES"
echo

"$GCLOUD" run services update "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --ingress all \
  --min-instances 0 \
  --max-instances "$MAX_INSTANCES" \
  --quiet

"$GCLOUD" run services add-iam-policy-binding "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --member allUsers \
  --role roles/run.invoker \
  --quiet

URL="$("$GCLOUD" run services describe "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --format='value(status.url)')"

echo
echo "Public access is resumed:"
echo "$URL"

if [[ "$SMOKE" == "1" ]]; then
  if command -v curl >/dev/null 2>&1; then
    echo
    echo "Smoke-checking /health ..."
    curl -fsS "$URL/health"
    echo
  else
    echo "curl not found; skipping /health smoke check."
  fi
else
  echo "SMOKE=$SMOKE; skipping /health smoke check."
fi
