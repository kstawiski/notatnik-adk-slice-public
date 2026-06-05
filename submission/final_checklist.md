# Final Submission Checklist

All package blockers are closed as of the latest QA pass. The final Devpost form review and Submit click are the remaining user-gated external actions.

## Required Artifacts

Devpost-required asset fields observed on the project edit page: `Video*`, `Code*`, `Testing access: link/demo/test build, with login if private*`, and `Architecture diagram*`.

| ID | Artifact | Status | Evidence / next action |
|---|---|---|---|
| A1 | Public Cloud Run demo URL | READY | https://notatnik-adk-slice-307066208186.europe-west1.run.app. Live smoke on 2026-06-05: `/health` OK, `/cases` has 18 cases and pre-run CASE-003 source preview, `CASE-003` QC PASS/self-corrected/generated scrub PASS with `[DISCREPANCY] cT2 N0 vs cT3 N1`. |
| A2 | 1-2 min video | READY | Captioned Chrome browser-flow take uploaded: https://chmura.radioonkolog.pl/s/nWsCwkRQDiLmJ4k. Direct download: https://chmura.radioonkolog.pl/s/nWsCwkRQDiLmJ4k/download. |
| A3 | Architecture diagram | READY | `architecture.svg`, `architecture.mmd`. |
| A4 | Public/judge-accessible code URL | READY | Repository URL: https://github.com/kstawiski/notatnik-adk-slice-public. Backup code folder URL: https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d; direct download: https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d/download. Code package QA: one root commit, no raw eval trace, no raw `agents/evidence/`, strict secret/key scan clean, tests and Docker smoke green. |
| A5 | Devpost write-up | READY | `devpost_writeup.md`; demo, code, and video URLs are filled. |
| A6 | Business one-pager | READY | `business_one_pager.md`. |
| A7 | Reliability delta table | READY | `reliability_delta.md`; C4 reliability profile finalized. |
| A8 | Auditable eval package | READY | `eval/` plus C4 report/output artifacts. |
| A9 | Grounding corpus | READY | `grounding/` committed PDQ corpus/index; raw scraped pages excluded. |
| A10 | Redacted trace/observability notes | READY | `trace_notes.md`; Chrome video test take and visual samples are available. |
| A11 | Devpost metadata | READY / FORM ACTION | Set Region=EMEA and Track=Optimize; final submitted status only after the Devpost Submit click. |
| A12 | Organizer email/reply | CHECKED BY USER | User reported on 2026-06-05 that the deadline/admission timing is OK. No package edit remains. |

## Remaining User-Gated External Actions

1. Paste the final Devpost fields from `devpost_writeup.md`.
2. Verify the Devpost preview one last time.
3. Click Submit.

The package now provides both a standard repository URL and a backup folder/direct-download URL.

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
- Public Cloud Run: revision `notatnik-adk-slice-00008-fwz` deployed in `europe-west1` with maxScale=2/minScale=0; live `/health`, `/cases`, Chrome first-screen/mobile/footer visual checks, and Chrome `CASE-003` UI run smoke green.

## Final QA Scan To Run After User-Gated Actions

```bash
git status --short
git log --oneline --all
docker build -f deploy/Dockerfile -t notatnik-adk-slice:final .
```

Also run an external secret scanner plus a manual forbidden-name/host scan before any public
push or Devpost paste.

Any public Cloud Run URL, code URL, video URL, or Devpost final text change reopens the final package QA gate.
