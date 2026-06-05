# Devpost Write-Up

## Project Title

Notatnik Medyczny: ADK Reliability Slice for Oncology Documentation

## Short Description

A physician-in-the-loop oncology documentation agent that uses ADK sub-agents, Gemini on Vertex AI, MCP tools, and deterministic safety checks to measure and improve source-grounded reliability on synthetic cases before clinical use.

Held-out prompt optimization improved source-grounded reliability by +0.115, and the live demo shows a rectal-cancer staging conflict surfaced as `[DISCREPANCY] cT2 N0 vs cT3 N1` rather than silently resolved.

## Track / Region / Entrant

- Track: Optimize
- Region: EMEA
- Entrant: Radioonkolog.pl / Konrad Stawiski, Prywatna Praktyka Lekarska
- Demo data: synthetic oncology cases only

Why Track 2: this is not a net-new chatbot. It is a contest-period hardening slice for an existing oncology documentation product, focused on making failure modes measurable and auditable.

Key optimization result: prompt optimization improved held-out source-grounded reliability by +0.115, while multi-agent QC exposed targeted contradictions but also revealed a synthetic PII regression mitigated by deterministic output scrubbing. The write-up is structured around the published judging weights: technical implementation, business case, innovation/creativity, and demo/presentation.

## Testing Access

Use these testing links:

- Demo URL: https://notatnik-adk-slice-307066208186.europe-west1.run.app
- Source code repository: https://github.com/kstawiski/notatnik-adk-slice-public
- Backup code folder: https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d
- Direct code download: https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d/download
- Video URL: https://chmura.radioonkolog.pl/s/nWsCwkRQDiLmJ4k
- Direct video download: https://chmura.radioonkolog.pl/s/nWsCwkRQDiLmJ4k/download

The public Cloud Run service was smoke-tested on 2026-06-05 with `/health`, `/cases`, first-screen CASE-003 source preview, and `CASE-003` (`include_evidence=false`). Do not paste local service URLs into Devpost.

## Problem

Oncology documentation is high-stakes and detail-heavy: staging, margins, nodal status, biomarkers, evidence citations, and trial prescreening all need to stay source-grounded. A generic note-generation agent can sound fluent while silently fabricating a cancer stage, missing a contradiction between documents, or leaking source identifiers.

Notatnik Medyczny is an existing clinical-documentation product with a public product site at https://notatnikmedyczny.pl. For this challenge, the submitted project is a new contest-period ADK reliability slice that optimizes a small but judgeable workflow: synthetic source documents go through a documentation agent, an independent QC agent, and an evidence agent, with a measured before/after reliability evaluation.

## What It Does

The demo service lets a judge run synthetic oncology cases through the ADK slice and inspect:

- the source case;
- the reliability target before optimization;
- the generated structured clinical summary;
- whether QC passed, rejected, and self-corrected;
- tool calls over a real MCP boundary;
- whether generated text passed deterministic source-identifier scrubbing.

The default demo case (`CASE-003`) is a rectal-cancer staging conflict. The agent must not silently choose one stage; it must surface the discrepancy and require clinician reconciliation.

## Google Cloud / Agent Technology Used

- Gemini reasoning via Vertex AI: `gemini-3.1-flash-lite`, project `gen-lang-client-0384080704`, location `global`.
- ADK orchestration: `SequentialAgent` with a `LoopAgent` review loop and separate `documentation`, `qc`, and `evidence` LLM sub-agents.
- MCP boundary: data tools are exposed through a real MCP stdio server and consumed through an ADK MCP toolset.
- Cloud Run target: a FastAPI judge UI/API packaged by Docker, using a runtime service account with Vertex AI permissions.
- Grounding: committed public NCI PDQ treatment-summary corpus and embedding index for local guideline retrieval; the demo does not depend on a private database, private search service, or production Notatnik runtime.

Track 2 optimization mapping: the synthetic oncology fixtures act as the agent-simulation layer, the held-out C4 harness is the agent-evaluation layer, and the structured `CaseRun` trace (`doc_drafts`, `qc_rejections`, `qc_passed`, tool calls, and scrub status) is the public observability layer. We kept these pieces self-contained to preserve clinical IP isolation, deterministic temperature-0 reproducibility, and gold-grounded grading for oncology documentation failures.

Platform-scope note: for the challenge artifact, we used ADK, Gemini via Vertex AI, MCP, Cloud Run, and a self-contained synthetic simulation/evaluation/trace harness. We describe those pieces as the Track 2 simulation, evaluation, and observability layers rather than claiming use of branded Agent Simulation, Agent Evaluation, Agent Observability, Agent Runtime, Agent Engine, or Agent Optimizer services.

## Data Sources and Rights

- Patient cases: invented synthetic oncology fixtures. No real PHI is present.
- Literature/trial lookups: deterministic synthetic records shaped like PubMed and ClinicalTrials.gov responses.
- Guideline grounding: NCI PDQ cancer treatment summaries, public-domain U.S. government content, cleaned into a committed corpus/index. The raw scraped pages are not shipped.
- Proprietary Notatnik prompts/templates/rubrics/recognizers: not included in the submitted repo, video, traces, or public demo.

## Measured Reliability Result

The C4 evaluation used 15 synthetic cases, 3 runs per case at temperature 0, and a held-out test split of 8 cases. The primary metric was a gold-grounded LLM grader; deterministic rules were used as a cross-check. This is a descriptive reliability profile, not a significance claim.

The +0.115 held-out single-agent gain is a transfer result from prompts selected on the multi-agent training composite; the grader was validated for style-neutrality before it was used as the primary metric.

Held-out headline:

- Prompt optimization is the robust generalizing win: single-agent optimized improved by +0.115 primary / +0.098 rule on held-out cases.
- On this small synthetic held-out split, the optimized single-agent arm reached 1.000 on the primary score.
- The multi-agent QC loop is targeted rather than uniformly better: it improved contradiction cases in training, but did not generalize on held-out cases and regressed one held-out synthetic PII case.
- C6 therefore keeps the C4 negative result honest and adds deterministic generated-output scrubbing as the indicated mitigation.

Key held-out cases:

- `E-CON-04`: baseline fabricated melanoma stage `pT2b`; optimized prompt correctly flagged the missing TNM stage.
- `E-PII-02`: prompt optimization removed identifiers, but the QC loop reintroduced synthetic patient name/MRN; C6 post-scrubbing mitigates that generated-output failure.

## Business Case

The beachhead is clinician-facing oncology documentation in Poland/EMEA, starting with radiation oncology and multidisciplinary oncology workflows where staging, evidence, and treatment-plan context are costly to reconstruct manually.

The commercial hypothesis is not "replace clinicians." It is:

- reduce documentation time per oncology encounter;
- make source-faithfulness and uncertainty visible;
- keep physicians in the approval loop;
- sell into practices and oncology centers that already need GDPR-aware clinical documentation.

The first external validation milestone is a physician-design-partner pilot measuring minutes saved per documentation-heavy oncology encounter, contradiction/gap capture rate, generated-output scrub findings, and post-review edit burden.

See `business_one_pager.md` for the ROI scenario and source-backed demand drivers.

## Innovation

The key architectural move is the explicit MCP data-tool boundary and public/private IP firewall:

- it satisfies the challenge's multi-agent/MCP cue;
- it protects proprietary clinical IP from the public submission license;
- it lets the public demo be fully synthetic and self-contained while still resembling the production product boundary.

The optimization story is also deliberately honest: the submitted project does not claim that multi-agent is always better. It shows where prompt optimization generalizes, where the QC loop helps, and where the QC loop creates a safety regression that requires deterministic mitigation.

## Safety and Limitations

- Synthetic patient data only.
- Physician-in-the-loop; no autonomous diagnosis or treatment decision.
- Deterministic generated-output scrub in the public Cloud Run service.
- n=15 synthetic cases; descriptive reliability profile only.
- No claim that the public demo is production clinical software.
- No proprietary clinical prompt/template/rubric/recognizer is submitted.

## Findings and Learnings

1. A fluent holistic judge can reward a fabricated but confident stage; the gold-grounded primary metric caught this.
2. Prompt optimization generalized better than the QC loop on held-out cases.
3. Multi-agent QC can be valuable for contradictions, but can also reintroduce identifiers; safety needs deterministic post-processing, not only LLM review.
4. A small ADK-on-Cloud-Run slice can make an existing healthcare agent judgeable without exposing clinical IP.

## Final Devpost Metadata Checklist

- Region: EMEA
- Theme/Track: Optimize
- Status: Pending until Devpost Submit click
- Testing access URL: https://notatnik-adk-slice-307066208186.europe-west1.run.app
- Video URL: https://chmura.radioonkolog.pl/s/nWsCwkRQDiLmJ4k
- Code URL: https://github.com/kstawiski/notatnik-adk-slice-public
