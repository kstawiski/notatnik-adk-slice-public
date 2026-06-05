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

SERVICE_JSON="$("$GCLOUD" run services describe "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --format=json)"

if command -v python3 >/dev/null 2>&1; then
  printf '%s' "$SERVICE_JSON" | python3 -c '
import json
import sys

service = json.load(sys.stdin)
metadata = service.get("metadata", {})
status = service.get("status", {})
template_metadata = service.get("spec", {}).get("template", {}).get("metadata", {})
annotations = metadata.get("annotations", {})
template_annotations = template_metadata.get("annotations", {})
containers = service.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
env_items = containers[0].get("env", []) if containers else []
env = {item.get("name"): item.get("value", "") for item in env_items}

rows = [
    ("service", metadata.get("name", "")),
    ("url", status.get("url", "")),
    ("ingress", annotations.get("run.googleapis.com/ingress", "all (default)")),
    ("minScale", template_annotations.get("autoscaling.knative.dev/minScale", "0 (default)")),
    ("maxScale", template_annotations.get("autoscaling.knative.dev/maxScale", "")),
    ("latestReadyRevision", status.get("latestReadyRevisionName", "")),
    ("runAccessToken", "configured" if env.get("RUN_ACCESS_TOKEN") else "missing"),
    ("runRateLimit", env.get("RUN_RATE_LIMIT_PER_MINUTE", "")),
    ("globalRunRateLimit", env.get("RUN_GLOBAL_RATE_LIMIT_PER_MINUTE", "")),
    ("allowEvidence", env.get("ALLOW_EVIDENCE", "")),
    ("maxAgentIterations", env.get("MAX_AGENT_ITERATIONS", "")),
]

width = max(len(k) for k, _ in rows)
for key, value in rows:
    print(f"{key:<{width}}  {value}")
'
else
  printf '%s\n' "$SERVICE_JSON"
fi

echo
echo "Invoker bindings:"
POLICY_JSON="$("$GCLOUD" run services get-iam-policy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --format=json)"

if command -v python3 >/dev/null 2>&1; then
  printf '%s' "$POLICY_JSON" | python3 -c '
import json
import sys

policy = json.load(sys.stdin)
found = False
for binding in policy.get("bindings", []):
    if binding.get("role") != "roles/run.invoker":
        continue
    for member in binding.get("members", []):
        found = True
        print(f"roles/run.invoker  {member}")
if not found:
    print("(none)")
'
else
  printf '%s\n' "$POLICY_JSON"
fi
