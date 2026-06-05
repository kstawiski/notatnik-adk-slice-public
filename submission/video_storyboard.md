# Demo Video Storyboard

Target length: 1:45-1:55. Only the first 2 minutes are evaluated.

Detailed recording plan: `video_recording_scenario.md`.

Do not show proprietary prompts, private backend code, real PHI, secrets, service-account files, browser tabs with unrelated patient systems, or unrelated institutional references.

## 0:00-0:13 - Opening

Narration:

"This is Notatnik Medyczny's Google AI Agents Challenge submission for Track 2 Optimize: an ADK reliability slice for an existing oncology documentation product. This public version is self-contained and synthetic only; production prompts, recognizers, and patient data stay outside the repo."

Screen:

- Demo home page: Header showing "Track 2 Optimize", "Gemini on Vertex AI", and "ADK + MCP".
- Cursor highlights "synthetic cases only".

## 0:13-0:31 - Reliability And Evaluation

Narration:

"The evaluation used 15 synthetic cases, three temperature-zero runs per case, and an eight-case held-out split. A gold-grounded LLM grader, checked for style neutrality, showed prompt optimization improved held-out reliability by plus 0.115. The honest negative: the QC loop reintroduced synthetic identifiers on E-PII-02, so the service now adds deterministic output scrubbing."

Screen:

- Open `submission/reliability_delta.md`.
- Highlight Evaluation setup, held-out test contrasts, `+0.115`, and `E-PII-02`.

## 0:31-0:45 - Source Conflict

Narration:

"Case-003 is the live test. The source documents conflict: MRI says cT2 N0, while the MDT note says cT3 N1. A safe documentation agent should not silently choose one."

Screen:

- Return to demo home page.
- Keep or select `CASE-003`.
- Point to the source preview before running: MRI (`cT2 N0`) vs MDT (`cT3 N1`).

## 0:45-1:03 - Live Agent Demo And Orchestration

Narration:

"We leave evidence retrieval off for speed. When I click Run, ADK orchestrates a documentation agent and a QC LoopAgent. The QC agent rechecks source data through MCP tools, and the response is released only after QC and scrub status pass."

Screen:

- Point to unchecked "Evidence" checkbox.
- Click the "Run Agent" button.
- Show "Running Vertex agent..." and use a jump-cut to display the finished run state.

## 1:03-1:18 - Summary Output And Scrub Gate

Narration:

"Here the final note preserves the discrepancy: cT2 N0 versus cT3 N1, requiring physician reconciliation. That is the core reliability behavior."

Screen:

- Scroll to the "After" panel in demo results.
- Highlight the metrics row (`QC = PASS`, `Self-corrected = yes`, `Generated scrub = PASS`).
- Highlight the discrepancy TNM staging line in the summary text.

## 1:18-1:30 - Cloud Run And Vertex Receipt

Narration:

"The health tab is the deployment receipt: FastAPI on Cloud Run, Gemini 3.1 Flash Lite through Vertex AI at global location, 18 synthetic cases loaded, and the PDQ grounding index present."

Screen:

- Switch to browser tab showing `/health`.
- Highlight JSON details: model, location, cases, and PDQ index availability.

## 1:30-1:45 - Architecture And IP Firewall

Narration:

"The architecture shows the Track 2 mapping: fixtures are simulation, the held-out harness is evaluation, and the CaseRun trace is observability. MCP is the data boundary, with public NCI PDQ grounding and no private clinical IP in the public artifact."

Screen:

- Switch to browser tab showing `architecture.svg`.
- Trace from Cloud Run, through ADK, across the MCP stdio boundary, to synthetic data tools and NCI PDQ grounding.

## 1:45-1:55 - Business ROI & Close

Narration:

"The business wedge is radiation oncology documentation: save repetitive note time, make uncertainty visible, and keep physicians in the approval loop. Prompt optimization generalized; multi-agent QC was targeted; deterministic safety mitigation was necessary."

Screen:

- Switch to browser tab showing `business_one_pager.md`.
- Focus on the ROI table (hours released and value).
- End on slide displaying the demo and code URLs.

## Recording Checklist

- Browser zoom: 110-125 percent for readability.
- Do not show terminals, IDE file trees, repo sidebars, shell prompts, ADC paths, or private env vars.
- If using the local service for recording before deploy, do not show the URL as final testing access.
- Use English narration or English subtitles.
- Keep under 2 minutes.
- Do not claim Agent Engine, Agent Runtime, Agent Optimizer, branded Google evaluation services, clinical validation, or statistical significance.
