#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${PROJECT:-gen-lang-client-0384080704}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-notatnik-adk-slice}"
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

echo "Stopping public access for Cloud Run service:"
echo "  project: $PROJECT"
echo "  region:  $REGION"
echo "  service: $SERVICE"
echo

"$GCLOUD" run services update "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --ingress internal \
  --min-instances 0 \
  --quiet

for member in allUsers allAuthenticatedUsers; do
  if "$GCLOUD" run services remove-iam-policy-binding "$SERVICE" \
    --project "$PROJECT" \
    --region "$REGION" \
    --member "$member" \
    --role roles/run.invoker \
    --quiet; then
    echo "Removed roles/run.invoker from $member."
  else
    echo "No roles/run.invoker binding for $member, or it was already removed."
  fi
done

URL="$("$GCLOUD" run services describe "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --format='value(status.url)')"

echo
echo "Public access is stopped. The service and revision remain available to resume."
echo "Service URL retained by Cloud Run: $URL"
echo "Resume with: PROJECT=$PROJECT REGION=$REGION SERVICE=$SERVICE bash deploy/resume-cloud-run.sh"
