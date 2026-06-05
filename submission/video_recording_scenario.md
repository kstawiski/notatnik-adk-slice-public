# Detailed Video Recording Scenario

Target length: 1:45-1:55. Hard cap: 2:00. Record in English, or add English subtitles.

Core message: the agent does not invent a stage; it surfaces uncertainty and forces clinician reconciliation.

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
| 0:00-0:11 | Demo home page | Start on the app header. Keep "Track 2 Optimize", "Gemini on Vertex AI", "ADK + MCP", and "synthetic oncology cases" visible. | "This is Notatnik Medyczny for Track 2 Optimize, a reliability slice for an existing oncology documentation product. The public demo uses synthetic cases only." |
| 0:11-0:25 | `reliability_delta.md` | Show headline and held-out table. Cursor can briefly point to `+0.115` and the QC-loop held-out row. | "Prompt optimization improved held-out source-grounded reliability by plus 0.115. The QC loop is targeted, not uniformly better, and a synthetic PII regression led to deterministic generated-output scrubbing." |
| 0:25-0:38 | Demo home page | Return to demo. Show `CASE-003` selected. Do not run yet. | "Our live case is a rectal-cancer staging conflict: MRI says cT2 N0, but the MDT note says cT3 N1. Instead of silently picking one, the agent surfaces the conflict." |
| 0:38-0:49 | Demo controls | Point to Evidence unchecked, then click Run. | "We disable evidence retrieval here for speed. Judges can enable it with this checkbox; the ADK and MCP boundaries remain visible in the trace." |
| 0:49-1:04 | Demo result | If the run takes more than 5 seconds, use one clean jump cut after showing "Running Vertex agent..." and continue on the same result. Show metrics row. | "The documentation agent drafts, the QC agent audits, and the loop passes once the contradiction is visible. This run self-corrected, passing QC and output scrubbing." |
| 1:04-1:14 | After panel | Highlight the TNM stage line containing `[DISCREPANCY]`, `cT2 N0`, and `cT3 N1`. | "The final note does not invent a stage. It states the discrepancy: cT2 N0 versus cT3 N1, requiring clinician reconciliation." |
| 1:14-1:26 | ADK Trace, then `/health` | Show tool calls in the trace briefly, then switch to `/health`. Point to `"model": "gemini-3.1-flash-lite"`, `"location": "global"`, and `"cases"`. | "The service runs on Cloud Run with FastAPI. The health check shows the pinned Gemini model, project, global location, and synthetic case count." |
| 1:26-1:38 | `architecture.svg` | Show the diagram. Move left to right: judge, Cloud Run, ADK, Vertex/MCP, synthetic data/PDQ, scrub. | "Under the hood are ADK agents, Gemini on Vertex, data tools over MCP, synthetic fixtures, public NCI PDQ grounding, and deterministic output scrubbing." |
| 1:38-1:47 | `business_one_pager.md` ROI table | Show annual time released and EUR value range. | "The business wedge: reduce repetitive documentation time, make staging uncertainty visible, and keep physicians in the loop." |
| 1:47-1:55 | Demo home page or closing slide | End on app or URLs after final deploy/push. | "Our learning: prompt optimization generalized; multi-agent QC is targeted; and deterministic safety scrubbing is required." |

## Exact Narration Script

Use this if reading from a teleprompter:

"This is Notatnik Medyczny for Track 2 Optimize, a reliability slice for an existing oncology documentation product. The public demo uses synthetic cases only.

Prompt optimization improved held-out source-grounded reliability by plus 0.115. The QC loop is targeted, not uniformly better, and a synthetic PII regression led to deterministic generated-output scrubbing.

Our live case is a rectal-cancer staging conflict: MRI says cT2 N0, but the MDT note says cT3 N1. Instead of silently picking one, the agent surfaces the conflict.

We disable evidence retrieval here for speed. Judges can enable it with this checkbox; the ADK and MCP boundaries remain visible in the trace.

The documentation agent drafts, the QC agent audits, and the loop passes once the contradiction is visible. This run self-corrected, passing QC and output scrubbing.

The final note does not invent a stage. It states the discrepancy: cT2 N0 versus cT3 N1, requiring clinician reconciliation.

The service runs on Cloud Run with FastAPI. The health check shows the pinned Gemini model, project, global location, and synthetic case count.

Under the hood are ADK agents, Gemini on Vertex, data tools over MCP, synthetic fixtures, public NCI PDQ grounding, and deterministic output scrubbing.

The business wedge: reduce repetitive documentation time, make staging uncertainty visible, and keep physicians in the loop.

Our learning: prompt optimization generalized; multi-agent QC is targeted; and deterministic safety scrubbing is required."

## Editing Rules

- Keep the first judged 2 minutes self-contained.
- Use at most one jump cut during the live run, only to remove wait time. Do not change case selection or Evidence state across the cut.
- Do not use music that competes with narration.
- Do not add decorative overlays that obscure metrics, the discrepancy line, or `/health`.
- If any run fails, do not record around it. Fix the service or use the last verified working deployment.
- If Self-corrected shows no but the note still surfaces the discrepancy, do not say "self-corrected." Replace that sentence with: "The run passes QC and output scrubbing, and the final note makes the contradiction visible."
- If evidence is enabled during a later take, say so clearly and budget extra time. The default recommended recording keeps Evidence unchecked.

## Required Final Frame

After public deploy, end on a clean screen or slide with:

- Demo URL: `https://notatnik-adk-slice-307066208186.europe-west1.run.app`
- Code URL: `https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d`
- Data note: synthetic cases only; no real PHI

Do not include local file paths or local service URLs in the final uploaded video.
