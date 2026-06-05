# C6 Cloud Run Deploy Notes

Do not deploy before the local tests and C6 review gate pass.

The service is self-contained:

- `MOCK_MODE=true`: patient data comes only from synthetic fixtures.
- `GROUNDING_PDQ=1`: guideline retrieval uses the committed NCI PDQ embedding index.
- Gemini reasoning uses Vertex AI through `agents.model.build_gemini()`.
- Runtime service account: `notatnik-adk-run@gen-lang-client-0384080704.iam.gserviceaccount.com`.

Build locally:

```bash
docker build -f deploy/Dockerfile -t notatnik-adk-slice:local .
docker run --rm -p 8080:8080 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/creds/adc.json \
  -v "$GOOGLE_APPLICATION_CREDENTIALS:/creds/adc.json:ro" \
  notatnik-adk-slice:local
```

Deploy after approval:

```bash
PROJECT=gen-lang-client-0384080704
REGION=europe-west1
REPO=notatnik-challenge
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/notatnik-adk-slice:$(date -u +%Y%m%dT%H%M%SZ)"

gcloud artifacts repositories create "$REPO" \
  --project "$PROJECT" --location "$REGION" --repository-format docker || true

gcloud builds submit --project "$PROJECT" \
  --config deploy/cloudbuild.yaml --substitutions _IMAGE="$IMAGE" .

gcloud run deploy notatnik-adk-slice \
  --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
  --service-account notatnik-adk-run@$PROJECT.iam.gserviceaccount.com \
  --allow-unauthenticated --min-instances 0 --max-instances 2 \
  --set-env-vars MOCK_MODE=true,GROUNDING_PDQ=1,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=global,RUN_TIMEOUT_SECONDS=180
```

`cloudrun.service.yaml` is a template for reviewers who prefer manifest-based deployment;
replace `IMAGE_URI_REPLACED_BY_DEPLOY` before applying it. The CLI command above is the
primary deployment path.

Post-deploy proof:

```bash
URL="$(gcloud run services describe notatnik-adk-slice --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
curl -fsS "$URL/healthz"
curl -fsS "$URL/cases" | head
```
