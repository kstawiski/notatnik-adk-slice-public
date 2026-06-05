# Submission Package

Working package for the Google for Startups AI Agents Challenge submission.

Status as of 2026-06-05:

- Track: Optimize
- Region: EMEA
- Entrant: Radioonkolog.pl / Konrad Stawiski
- Public demo: Cloud Run is live at https://notatnik-adk-slice-307066208186.europe-west1.run.app.
  Live smoke is green for `/health`, `/cases`, first-screen CASE-003 source preview, and `CASE-003` with evidence off.
- Code: public/judge-accessible folder ready at https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d.
  Direct download: https://chmura.radioonkolog.pl/s/syZbGTdHpMEHa3d/download.
  Export QA is green: one root commit, raw traces absent, strict secret/key scan clean, tests
  and Docker/container smoke passed.
- Video: storyboard is ready; a Chrome browser-flow test take was recorded and visually sampled, but final upload/subtitles-or-narration decision and Devpost video URL still need to happen.
- Devpost: write-up draft is ready with demo/code URLs filled; video URL and Submit click remain.

Artifacts:

- `devpost_writeup.md` - Devpost text fields and final paste-ready narrative.
- `business_one_pager.md` - business case and ROI model.
- `reliability_delta.md` - reviewed C4 result narrative and tables to paste into Devpost/video.
- `architecture.svg` and `architecture.mmd` - architecture diagram assets.
- `video_storyboard.md` - 1-2 minute demo video script and shot list.
- `trace_notes.md` - redacted trace/observability notes for screenshots or Devpost.
- `final_checklist.md` - submission status, blockers, and approval-gated actions.

Do not submit until `final_checklist.md` has no open blocker rows.
