# Demo Video Storyboard

Target length: 1:45-1:55. Only the first 2 minutes are evaluated.

Detailed recording plan: `video_recording_scenario.md`.

Do not show proprietary prompts, private backend code, real PHI, secrets, service-account files, browser tabs with unrelated patient systems, or unrelated institutional references.

## 0:00-0:12 - Opening

Narration:

"This is Notatnik Medyczny's Google AI Agents Challenge submission for Track 2 Optimize. It is a new ADK reliability slice for an existing oncology documentation product. The public demo uses synthetic cases only."

Screen:

- Title slide or service home page.
- Show "Track 2 Optimize", "EMEA", "synthetic data only".

## 0:12-0:38 - The Reliability Problem

Narration:

"In oncology documentation, a fluent agent is not enough. It can fabricate a cancer stage, miss a contradiction between reports, or reintroduce identifiers. We made those failures measurable."

Screen:

- `submission/reliability_delta.md` headline table or C4 report excerpt.
- Highlight `E-CON-04`: fabricated `pT2b` fixed by optimized prompt.
- Highlight the honest negative: QC reintroduced identifiers on `E-PII-02`.

## 0:38-1:10 - Live Agent Demo

Narration:

"Here is the Cloud Run judge surface running a synthetic rectal-cancer case. The source documents conflict: MRI says cT2 N0, while the MDT note says cT3 N1. The agent does not invent a stage; it surfaces uncertainty and forces clinician reconciliation. The ADK documentation agent drafts, the QC agent independently audits, and the loop only passes once the discrepancy is surfaced."

Screen:

- Open the service.
- Select or keep default `CASE-003`.
- Run with evidence retrieval disabled for the fast demo; the submitted service includes the evidence option and judges can enable it from the run controls.
- Show metrics: QC passed, self-corrected, generated scrub PASS.
- Show the after summary line: `[DISCREPANCY] TNM stage: cT2 N0 (MRI) vs cT3 N1 (MDT)`.

## 1:10-1:30 - Architecture / Google Tech Receipt

Narration:

"The slice is built on ADK sub-agents, real MCP tools, Gemini through Vertex AI, and a self-contained Cloud Run deployment. The production product remains separate from the public synthetic demo; no proprietary clinical prompts or recognizers are in the public repo."

Screen:

- `submission/architecture.svg`.
- Optional browser/API receipts:
  - A browser tab at `/health` shows model, project, location, cases.
  - A redacted `/run` response can show QC status and generated-output scrub PASS.

## 1:30-1:50 - Business and Close

Narration:

"The business wedge is oncology documentation: save physician time while making reliability visible and keeping clinicians in the approval loop. The key learning is honest optimization: prompt optimization generalized; multi-agent QC helped targeted contradictions but needed deterministic safety mitigation. That is what this submission demonstrates."

Screen:

- `submission/business_one_pager.md` ROI table.
- End on demo URL and code URL after final deploy.

## Recording Checklist

- Browser zoom: 110-125 percent for readability.
- Do not show terminals, IDE file trees, repo sidebars, shell prompts, ADC paths, or private env vars.
- If using the local service for recording before deploy, do not show the URL as final testing access.
- Use English narration or English subtitles.
- Keep under 2 minutes.
