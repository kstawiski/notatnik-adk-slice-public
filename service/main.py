"""C6 FastAPI entrypoint for the self-contained Cloud Run demo."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.model import LOCATION, MODEL_ID, PROJECT  # noqa: E402
from agents.pipeline import CaseRun, run_case  # noqa: E402
from grounding.retriever import index_available  # noqa: E402
from tools import data_tools  # noqa: E402
from tools.safety import contains_sensitive_term, sensitive_terms_from_source, scrub_mapping  # noqa: E402

DEFAULT_CASE = "CASE-003"
STATIC = Path(__file__).resolve().parent / "static"
INDEX_HTML = (STATIC / "index.html").read_text()
LOG = logging.getLogger(__name__)


class RunRequest(BaseModel):
    case_id: str = Field(default=DEFAULT_CASE, min_length=1)
    max_iterations: int = Field(default=4, ge=1, le=6)
    include_evidence: bool = False


def create_app() -> FastAPI:
    app = FastAPI(title="Notatnik ADK Reliability Slice", version="0.6.0")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "mock_mode": data_tools.mock_mode(),
            "grounding_pdq": os.environ.get("GROUNDING_PDQ", "unset"),
            "model": MODEL_ID,
            "project": PROJECT,
            "location": LOCATION,
            "cases": len(data_tools.list_cases()),
            "pdq_index_available": index_available(),
        }

    @app.get("/cases")
    async def cases() -> list[dict[str, Any]]:
        return sorted(data_tools.list_cases(), key=lambda item: item["case_id"])

    @app.post("/run")
    async def run(req: RunRequest) -> dict[str, Any]:
        known = {case["case_id"] for case in data_tools.list_cases()}
        if req.case_id not in known:
            raise HTTPException(status_code=404, detail=f"Unknown case_id: {req.case_id}")
        try:
            result = await asyncio.wait_for(
                run_case(
                    req.case_id,
                    max_iterations=req.max_iterations,
                    scrub_output=True,
                    include_evidence=req.include_evidence,
                ),
                timeout=float(os.environ.get("RUN_TIMEOUT_SECONDS", "180")),
            )
        except TimeoutError as exc:
            LOG.warning("Agent run timed out for case_id=%s", req.case_id, exc_info=True)
            raise HTTPException(status_code=504, detail="Agent run timed out") from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to judges as a service failure, not hidden
            LOG.exception("Agent run failed for case_id=%s", req.case_id)
            raise HTTPException(status_code=502, detail=f"Agent run failed: {type(exc).__name__}") from exc
        return _response_from_run(result, include_evidence=req.include_evidence)

    return app


def _response_from_run(run: CaseRun, *, include_evidence: bool = True) -> dict[str, Any]:
    source = data_tools.get_document_text(run.case_id)
    title = _title_for(run.case_id)
    terms = sensitive_terms_from_source(source)
    state = scrub_mapping(run.state, source)
    trace = [scrub_mapping(event, source) for event in run.events]
    combined_output = "\n".join([
        str(state.get("draft") or ""),
        str(state.get("evidence") or ""),
        str(trace),
    ])

    return {
        "case_id": run.case_id,
        "title": title,
        "source": {
            "document_count": _document_count(run.case_id),
            "text": source,
            "synthetic": True,
        },
        "before": _before_story(run.case_id),
        "after": {
            "draft": state.get("draft") or "",
            "evidence": state.get("evidence") or "",
            "evidence_requested": include_evidence,
        },
        "safety": {
            "post_scrub": True,
            "redacted_terms": len(terms),
            "contains_source_identifier_after_scrub": contains_sensitive_term(combined_output, terms),
        },
        "trace": {
            "doc_drafts": run.doc_drafts,
            "qc_rejections": run.qc_rejections,
            "qc_passed": run.qc_passed,
            "self_corrected": run.self_corrected,
            "tool_calls": run.tool_calls(),
            "events": trace,
        },
        "vertex": {"model": MODEL_ID, "project": PROJECT, "location": LOCATION},
    }


def _title_for(case_id: str) -> str:
    for case in data_tools.list_cases():
        if case["case_id"] == case_id:
            return str(case["title"])
    return case_id


def _document_count(case_id: str) -> int:
    for case in data_tools.list_cases():
        if case["case_id"] == case_id:
            return int(case["n_documents"])
    return 0


def _before_story(case_id: str) -> dict[str, str]:
    stories = {
        "CASE-002": {
            "label": "Unhardened behavior",
            "text": "A weak draft can leave staging vague or invent a TNM value when no TNM stage is documented.",
        },
        "CASE-003": {
            "label": "Unhardened behavior",
            "text": "A weak draft can silently pick one of two conflicting rectal-cancer stages instead of surfacing the conflict.",
        },
        "E-CON-04": {
            "label": "Observed C4 baseline failure",
            "text": "The baseline fabricated melanoma stage pT2b; the optimized prompt correctly flagged the missing TNM stage and retained the Breslow discrepancy.",
        },
        "E-PII-02": {
            "label": "Observed C4 safety regression",
            "text": "The QC loop reintroduced the synthetic patient name and MRN; C6 adds deterministic post-generation scrubbing.",
        },
    }
    return stories.get(
        case_id,
        {
            "label": "Reliability target",
            "text": "The hardened slice should preserve source-grounded clinical facts, surface gaps, and remove source identifiers.",
        },
    )


app = create_app()
