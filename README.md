# Notatnik Medyczny — ADK Reliability Slice (Google AI Agents Challenge, Track 2)

A new ADK multi-agent slice that reasons on **Gemini via Vertex AI** and models a
clinical-documentation backend boundary through synthetic MCP data tools. Engineering
layer only — no clinical IP. Synthetic data only.

## Layout

- `vertex_check/` — C1 green-assertion: proves reasoning runs on Vertex (`aiplatform`), not
  AI Studio. Run: `python3 vertex_check/assert_vertex.py` (see `evidence/`).
- `tools/` + `mcp_server/` — C2: deterministic synthetic DATA tools (`MOCK_MODE` default,
  no DB/GPU/network) exposed over a real **MCP** stdio server. The judged artifact runs
  entirely on these fixtures.
- `prompts/` — sanitized, non-proprietary demo prompts (the proprietary product prompts,
  rubrics, and recognizers never enter this repo).
- `agents/` — C3: the multi-agent reliability slice. A deterministic workflow orchestrator
  (`SequentialAgent`) wraps a self-correcting review loop and an evidence step:

  ```
  orchestrator (SequentialAgent)
    ├─ review_loop (LoopAgent)
    │    ├─ documentation (LlmAgent)  → structured summary  (state: draft)
    │    └─ qc           (LlmAgent)   → audits draft; exit_loop on PASS,
    │                                    else defect list    (state: qc_feedback)
    └─ evidence (LlmAgent)            → citations for the QC-passed summary
  ```

  All three LLM agents reason on Gemini via the shared C1 Vertex client and consume the C2
  tools over a real ADK **MCP toolset** (stdio). QC halts on an injected error (missing TNM
  / staging contradiction) and the loop self-corrects.
- `service/` + `deploy/` - C6: FastAPI judge UI/API for Cloud Run. It wraps the ADK run,
  returns a before/after reliability trace, and applies a deterministic non-proprietary
  source-identifier scrub before generated draft/evidence/trace text is returned.

## Run

```bash
python3 run_demo.py --case CASE-003 --write-trace # end-to-end on Vertex; writes a JSON trace
python3 tests/test_c2.py                          # C2: determinism + real MCP round-trip
python3 tests/test_c3.py                          # C3 wiring: MCP lists 5 tools + graph shape (no LLM)
python3 -m pytest tests/test_c6.py -q             # C6 API + safety post-scrub, no Vertex
uvicorn service.main:app --host 0.0.0.0 --port 8080
```

Synthetic cases: `CASE-001` (clean) · `CASE-002` (missing TNM → QC validates the data-gap
flag) · `CASE-003` (contradictory staging → QC catches it, the draft self-corrects).

C4 found that the QC loop can re-introduce identifiers on one held-out synthetic PII case.
C6 keeps that measurement intact and adds the indicated mitigation: the Cloud Run API/UI
post-scrubs generated text and exposes a generated-output scrub PASS/HOLD flag.

## Judge Quick Checks

- One-command local demo: `python3 run_demo.py --case CASE-003 --write-trace`.
- One-command API safety test: `python3 -m pytest tests/test_c6.py -q`.
- Full offline test suite: `python3 -m pytest tests eval/tests -q`.
- Cloud Run deployment notes: `deploy/README.md`.
- Synthetic data statement: all patient cases and literature/trial fixtures are invented; no real PHI is present.
- License: MIT, see `LICENSE`.
- NCI PDQ attribution and data-rights note: `grounding/README.md`.
- Expected `CASE-003` behavior: the final summary should surface `[DISCREPANCY] TNM stage: cT2 N0 (MRI) vs cT3 N1 (MDT)`, and the generated-output scrub should report PASS.
