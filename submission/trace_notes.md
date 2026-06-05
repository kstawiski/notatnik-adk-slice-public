# Redacted Trace / Observability Notes

Use these notes for Devpost screenshots or video overlays. They contain no real PHI and no proprietary prompts.

## C6 Live Demo Trace

Case: `CASE-003` (synthetic rectal-cancer staging conflict)

Request:

```json
{"case_id":"CASE-003","max_iterations":4,"include_evidence":false}
```

Observed live Cloud Run result on 2026-06-05 (`notatnik-adk-slice-00008-fwz`):

```json
{
  "case_id": "CASE-003",
  "qc_passed": true,
  "self_corrected": true,
  "doc_drafts": 4,
  "qc_rejections": 3,
  "contains_source_identifier_after_scrub": false,
  "evidence_requested": false
}
```

Key generated summary excerpt:

```text
Diagnosis: Rectal adenocarcinoma
TNM stage: [DISCREPANCY] TNM stage: cT2 N0 (MRI) vs cT3 N1 (MDT) - requires clinician reconciliation
Key biomarkers: [DATA GAP] Key biomarkers not documented in source
Margins / nodes: [DATA GAP] Margins not documented in source
```

## What To Show

- ADK loop behavior: documentation drafts > QC rejects > final QC pass.
- Tool boundary: source is fetched through the MCP tool layer, not direct private backend calls.
- Safety: generated-output scrub flag is PASS.
- Vertex provenance: `/health` exposes `gemini-3.1-flash-lite`, project `gen-lang-client-0384080704`, location `global`.

## What Not To Show

- Real patient data.
- Production prompts/templates/rubrics/recognizers.
- Service-account key files or ADC JSON.
- Raw `agents/evidence/` demo traces unless inspected and redacted first.
- Any screen or text mentioning unrelated institutions.
