#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${PROJECT:-gen-lang-client-0384080704}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-notatnik-adk-slice}"
MAX_INSTANCES="${MAX_INSTANCES:-2}"
RUN_ACCESS_TOKEN="${RUN_ACCESS_TOKEN:-}"
ALLOW_UNPROTECTED_RUN="${ALLOW_UNPROTECTED_RUN:-0}"
ALLOW_EVIDENCE="${ALLOW_EVIDENCE:-false}"
RUN_RATE_LIMIT_PER_MINUTE="${RUN_RATE_LIMIT_PER_MINUTE:-4}"
RUN_GLOBAL_RATE_LIMIT_PER_MINUTE="${RUN_GLOBAL_RATE_LIMIT_PER_MINUTE:-8}"
RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-180}"
MAX_AGENT_ITERATIONS="${MAX_AGENT_ITERATIONS:-4}"
MAX_REQUEST_BYTES="${MAX_REQUEST_BYTES:-4096}"
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

if [[ -z "$RUN_ACCESS_TOKEN" && "$ALLOW_UNPROTECTED_RUN" != "1" ]]; then
  echo "RUN_ACCESS_TOKEN is required before resuming public access to the Vertex-backed /run endpoint." >&2
  echo "Generate one with: LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32" >&2
  echo "Override only for local debugging with ALLOW_UNPROTECTED_RUN=1." >&2
  exit 2
fi

echo "Resuming public access for Cloud Run service:"
echo "  project:       $PROJECT"
echo "  region:        $REGION"
echo "  service:       $SERVICE"
echo "  max instances: $MAX_INSTANCES"
echo "  /run token:    $([[ -n "$RUN_ACCESS_TOKEN" ]] && echo configured || echo disabled)"
echo

ENV_VARS="RUN_TIMEOUT_SECONDS=$RUN_TIMEOUT_SECONDS,MAX_AGENT_ITERATIONS=$MAX_AGENT_ITERATIONS,MAX_REQUEST_BYTES=$MAX_REQUEST_BYTES,RUN_RATE_LIMIT_PER_MINUTE=$RUN_RATE_LIMIT_PER_MINUTE,RUN_GLOBAL_RATE_LIMIT_PER_MINUTE=$RUN_GLOBAL_RATE_LIMIT_PER_MINUTE,ALLOW_EVIDENCE=$ALLOW_EVIDENCE"
if [[ -n "$RUN_ACCESS_TOKEN" ]]; then
  ENV_VARS="$ENV_VARS,RUN_ACCESS_TOKEN=$RUN_ACCESS_TOKEN"
fi

"$GCLOUD" run services update "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --ingress all \
  --min-instances 0 \
  --max-instances "$MAX_INSTANCES" \
  --update-env-vars "$ENV_VARS" \
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
