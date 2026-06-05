# Detailed Video Recording Scenario

Target length: 1:45-1:55. Hard cap: 2:00. Record in English, or add English subtitles.

Core message: the agent does not invent a stage; it surfaces uncertainty and forces clinician reconciliation.

## Background and Technical Emphasis

The video should quickly answer four questions before the first two minutes end:

- What this is: a Track 2 Optimize reliability slice for an existing oncology documentation product.
- What was measured: 15 synthetic cases, 3 temperature-0 runs per case, 8 held-out test cases, a gold-grounded primary grader, and deterministic rule cross-checks.
- What the live run proves: the agent reads conflicting source documents, surfaces the staging discrepancy, passes QC, and passes generated-output scrubbing before the note is shown.
- What the architecture proves: ADK orchestration, Gemini on Vertex AI, MCP data-tool boundary, Cloud Run deployment, public NCI PDQ grounding, and a public/private IP firewall.

Useful Track 2 phrasing: the synthetic fixtures are the simulation layer, the held-out harness is the evaluation layer, and the structured `CaseRun` trace is the observability layer.

## Pre-Recording Setup

Use a clean browser profile or a window with no unrelated tabs. Hide bookmarks if they contain private context. Browser zoom: 110-125 percent. Record at 1080p or higher.

Open only these tabs:

1. Public Cloud Run demo home page.
2. Public Cloud Run `/health`.
3. `submission/architecture.svg`.
4. `submission/reliability_delta.md`, focused on the headline and held-out table.
5. `submission/business_one_pager.md`, focused on the ROI table.

If recording local files before final deployment, crop or hide the address bar so local paths are not visible. Do not present a localhost URL as the final Devpost testing-access URL.

Record from browser tabs only. Do not show an IDE file tree, terminal directory listing, repository sidebar, or shell prompt.

Prepare the demo tab:

- Keep default case `CASE-003 - Rectal cancer - conflicting T-stage`.
- Leave `Evidence` unchecked for the fast recording.
- Confirm the Run button, Evidence checkbox, and metrics row are visible.
- Pre-warm the service by loading `/health` and `/cases` before recording.
- Dry-run `CASE-003` before the final take. Record only if the metrics row shows QC = PASS, Self-corrected = yes, Generated scrub = PASS, and the After pane contains a TNM stage line with `[DISCREPANCY]`, `cT2 N0`, and `cT3 N1`. If the run passes QC on the first draft and Self-corrected shows no, re-run or use the fallback narration in Editing Rules.

Do not show proprietary prompts, private backend code, real PHI, service-account files, ADC JSON, environment variables, unrelated institutional tabs, raw `agents/evidence/` traces, or the removed service-account assertion receipt.

## Recording Flow

| Time | Screen | Action | Narration |
|---|---|---|---|
| 0:00-0:13 | Demo home page | Start on the app header. Keep "Track 2 Optimize", "Gemini on Vertex AI", "ADK + MCP", and "synthetic oncology cases" visible. | "This is Notatnik Medyczny's Google AI Agents Challenge submission for Track 2 Optimize: an ADK reliability slice for an existing oncology documentation product. This public version is self-contained and synthetic only; production prompts, recognizers, and patient data stay outside the repo." |
| 0:13-0:31 | `reliability_delta.md` | Show Evaluation setup, headline, and held-out test contrasts. Cursor highlights 15 cases, 8 held-out cases, `+0.115`, and `E-PII-02`. | "The evaluation used 15 synthetic cases, three temperature-zero runs per case, and an eight-case held-out split. A gold-grounded LLM grader, checked for style neutrality, showed prompt optimization improved held-out reliability by plus 0.115. The honest negative: the QC loop reintroduced synthetic identifiers on E-PII-02, so the service now adds deterministic output scrubbing." |
| 0:31-0:45 | Demo home page | Return to demo. Show `CASE-003` selected and briefly point to the source preview: MRI (`cT2 N0`) vs MDT (`cT3 N1`). Do not run yet. | "Case-003 is the live test. The source documents conflict: MRI says cT2 N0, while the MDT note says cT3 N1. A safe documentation agent should not silently choose one." |
| 0:45-1:03 | Demo controls & run | Point to Evidence unchecked, then click Run. Show "Running Vertex agent..." and use one jump cut if needed. | "We leave evidence retrieval off for speed. When I click Run, ADK orchestrates a documentation agent and a QC LoopAgent. The QC agent rechecks source data through MCP tools, and the response is released only after QC and scrub status pass." |
| 1:03-1:18 | Demo result / After panel | Show metrics row (QC passed, self-corrected, generated scrub PASS), then highlight the discrepancy line. | "Here the final note preserves the discrepancy: cT2 N0 versus cT3 N1, requiring physician reconciliation. That is the core reliability behavior." |
| 1:18-1:30 | `/health` endpoint | Switch to `/health`. Point to `"model": "gemini-3.1-flash-lite"`, `"location": "global"`, `"cases": 18`, and `"pdq_index_available": true`. | "The health tab is the deployment receipt: FastAPI on Cloud Run, Gemini 3.1 Flash Lite through Vertex AI at global location, 18 synthetic cases loaded, and the PDQ grounding index present." |
| 1:30-1:45 | `architecture.svg` | Show the diagram. Move left to right: Cloud Run, ADK loop, Vertex Gemini, MCP stdio boundary, synthetic fixtures, NCI PDQ, scrub. | "The architecture shows the Track 2 mapping: fixtures are simulation, the held-out harness is evaluation, and the CaseRun trace is observability. MCP is the data boundary, with public NCI PDQ grounding and no private clinical IP in the public artifact." |
| 1:45-1:55 | `business_one_pager.md` / Close | Show ROI table. End on final slide/URLs. | "The business wedge is radiation oncology documentation: save repetitive note time, make uncertainty visible, and keep physicians in the approval loop. Prompt optimization generalized; multi-agent QC was targeted; deterministic safety mitigation was necessary." |

## Exact Narration Script

Use this if reading from a teleprompter:

"This is Notatnik Medyczny's Google AI Agents Challenge submission for Track 2 Optimize: an ADK reliability slice for an existing oncology documentation product. This public version is self-contained and synthetic only; production prompts, recognizers, and patient data stay outside the repo.

The evaluation used 15 synthetic cases, three temperature-zero runs per case, and an eight-case held-out split. A gold-grounded LLM grader, checked for style neutrality, showed prompt optimization improved held-out reliability by plus 0.115. The honest negative: the QC loop reintroduced synthetic identifiers on E-PII-02, so the service now adds deterministic output scrubbing.

Case-003 is the live test. The source documents conflict: MRI says cT2 N0, while the MDT note says cT3 N1. A safe documentation agent should not silently choose one.

We leave evidence retrieval off for speed. When I click Run, ADK orchestrates a documentation agent and a QC LoopAgent. The QC agent rechecks source data through MCP tools, and the response is released only after QC and scrub status pass.

Here the final note preserves the discrepancy: cT2 N0 versus cT3 N1, requiring physician reconciliation. That is the core reliability behavior.

The health tab is the deployment receipt: FastAPI on Cloud Run, Gemini 3.1 Flash Lite through Vertex AI at global location, 18 synthetic cases loaded, and the PDQ grounding index present.

The architecture shows the Track 2 mapping: fixtures are simulation, the held-out harness is evaluation, and the CaseRun trace is observability. MCP is the data boundary, with public NCI PDQ grounding and no private clinical IP in the public artifact.

The business wedge is radiation oncology documentation: save repetitive note time, make uncertainty visible, and keep physicians in the approval loop. Prompt optimization generalized; multi-agent QC was targeted; deterministic safety mitigation was necessary."


## Editing Rules

- Keep the first judged 2 minutes self-contained.
- Use at most one jump cut during the live run, only to remove wait time. Do not change case selection or Evidence state across the cut.
- Do not use music that competes with narration.
- Do not add decorative overlays that obscure metrics, the discrepancy line, or `/health`.
- If any run fails, do not record around it. Fix the service or use the last verified working deployment.
- If Self-corrected shows no but the note still surfaces the discrepancy, do not say "self-corrected." Replace that sentence with: "The run passes QC and output scrubbing, and the final note makes the contradiction visible."
- If evidence is enabled during a later take, say so clearly and budget extra time. The default recommended recording keeps Evidence unchecked.
- Do not claim use of Agent Engine, Agent Runtime, Agent Optimizer, or branded Google evaluation services unless those artifacts are actually added.
- Do not claim statistical significance, clinical validation, autonomous treatment decisions, or production medical-device readiness.

## Required Final Frame

After public deploy, end on a clean screen or slide with:

- Demo URL: `https://notatnik-adk-slice-307066208186.europe-west1.run.app`
- Code URL: `https://github.com/kstawiski/notatnik-adk-slice-public`
- Backup code package: `https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d`
- Data note: synthetic cases only; no real PHI

Do not include local file paths or local service URLs in the final uploaded video.
