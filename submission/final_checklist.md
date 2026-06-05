# Final Submission Checklist

Do not submit until every blocker is closed.

## Required Artifacts

Devpost-required asset fields observed on the project edit page: `Video*`, `Code*`, `Testing access: link/demo/test build, with login if private*`, and `Architecture diagram*`.

| ID | Artifact | Status | Evidence / next action |
|---|---|---|---|
| A1 | Public Cloud Run demo URL | BLOCKED | Local C6 service green; deploy requires explicit user approval. Fill `PASTE_CLOUD_RUN_URL_AFTER_APPROVED_DEPLOY`. |
| A2 | 1-2 min video | TODO | `video_storyboard.md` is ready; record, upload, paste URL. |
| A3 | Architecture diagram | READY | `architecture.svg`, `architecture.mmd`. |
| A4 | Public/judge-accessible code URL | READY | Code folder URL: https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d; direct download: https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d/download. Code package QA: one root commit, no raw eval trace, no raw `agents/evidence/`, strict secret/key scan clean, tests and Docker smoke green. |
| A5 | Devpost write-up | DRAFT READY | `devpost_writeup.md`; code URL is filled; fill demo and video URLs after final actions. |
| A6 | Business one-pager | READY | `business_one_pager.md`. |
| A7 | Reliability delta table | READY | `reliability_delta.md`; C4 reliability profile finalized. |
| A8 | Auditable eval package | READY | `eval/` plus C4 report/output artifacts. |
| A9 | Grounding corpus | READY | `grounding/` committed PDQ corpus/index; raw scraped pages excluded. |
| A10 | Redacted trace/observability notes | DRAFT READY | `trace_notes.md`; screenshots/video still need recording. |
| A11 | Devpost metadata | TODO | Set Region=EMEA and Track=Optimize; final submitted status only after the Devpost Submit click. |
| A12 | Organizer email/reply | TODO | Confirm if already sent; log reply if available. |

## Hard Blockers Before Public Submission

1. User-approved Cloud Run deploy and smoke test of public URL.
2. Video recorded/uploaded.
3. Devpost final fields completed and Submit clicked.

Code access is available as a public folder share. If Devpost rejects a folder/share link and requires a repository-style URL, create a public remote from `adk-slice-public/` and replace the code URL before final submission.

## Completed Work

- C1 Vertex assertion: GREEN.
- C2 synthetic tools/MCP: DONE.
- C3 ADK multi-agent slice: DONE.
- C4 reliability eval: finalized; plausibility floor passed.
- C5 grounding: DONE.
- C6 Cloud Run service package: FastAPI UI/API, Docker/Cloud Run scaffolding, and generated-output scrub implemented.
- C6 tests: `tests/test_c6.py`; full offline suite: `tests eval/tests`.
- C6 Docker: build, image inventory, and container smoke green.
- C6 plausibility/safety floor: deterministic floor PASS; no residual identifiers after generated-output scrub probes.
- Public package QA: one root commit, raw C4 `runs.jsonl` excluded, tracked demo traces removed, targeted forbidden/secret scan clean, public-export tests and Docker/container smoke green.

## Final QA Scan To Run After User-Gated Actions

```bash
git status --short
git log --oneline --all
docker build -f deploy/Dockerfile -t notatnik-adk-slice:final .
```

Also run an external secret scanner plus a manual forbidden-name/host scan before any public
push or Devpost paste.

Any public Cloud Run URL, code URL, video URL, or Devpost final text change reopens the final package QA gate.
