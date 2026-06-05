"""C6 FastAPI entrypoint for the self-contained Cloud Run demo."""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import sys
import time
from collections import defaultdict, deque
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
_RATE_LOCK = asyncio.Lock()
_CACHE_LOCK = asyncio.Lock()
_RUN_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_GLOBAL_BUCKET: deque[float] = deque()
_RUN_CACHE: dict[tuple[str, str, int, bool], tuple[float, dict[str, Any]]] = {}


class RunRequest(BaseModel):
    case_id: str = Field(default=DEFAULT_CASE, min_length=1)
    max_iterations: int = Field(default=4, ge=1, le=6)
    include_evidence: bool = False


def create_app() -> FastAPI:
    app = FastAPI(title="Notatnik ADK Reliability Slice", version="0.6.0")

    @app.middleware("http")
    async def request_size_guard(request: Request, call_next):
        if request.url.path == "/run":
            max_bytes = _env_int("MAX_REQUEST_BYTES", 4096, minimum=1)
            raw_length = request.headers.get("content-length")
            if raw_length:
                try:
                    length = int(raw_length)
                except ValueError:
                    return JSONResponse({"detail": "Invalid Content-Length header"}, status_code=400)
                if length > max_bytes:
                    return JSONResponse(
                        {"detail": f"Request body is too large; limit is {max_bytes} bytes"},
                        status_code=413,
                    )
            body = await request.body()
            if len(body) > max_bytes:
                return JSONResponse(
                    {"detail": f"Request body is too large; limit is {max_bytes} bytes"},
                    status_code=413,
                )

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive  # noqa: SLF001 - Starlette has no public body replay hook.
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML)

    @app.get("/health")
    @app.get("/healthz")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mock_mode": data_tools.mock_mode(),
            "grounding_pdq": os.environ.get("GROUNDING_PDQ", "unset"),
            "model": MODEL_ID,
            "project_configured": bool(PROJECT),
            "location": LOCATION,
            "cases": len(data_tools.list_cases()),
            "pdq_index_available": index_available(),
            "run_auth_required": bool(_run_access_token()),
            "run_rate_limited": _env_int("RUN_RATE_LIMIT_PER_MINUTE", 4, minimum=0) > 0
            or _env_int("RUN_GLOBAL_RATE_LIMIT_PER_MINUTE", 8, minimum=0) > 0,
            "max_agent_iterations": _env_int("MAX_AGENT_ITERATIONS", 4, minimum=1, maximum=6),
            "evidence_enabled": _env_bool("ALLOW_EVIDENCE", True),
            "mock_fallback_enabled": bool(_run_access_token()),
        }

    @app.get("/auth/status")
    async def auth_status(request: Request) -> dict[str, Any]:
        auth = _run_auth_status(request)
        return {
            **auth,
            "auth_required": bool(_run_access_token()),
            "evidence_available": auth["run_mode"] == "real" and _env_bool("ALLOW_EVIDENCE", True),
        }

    @app.get("/cases")
    async def cases() -> list[dict[str, Any]]:
        items = sorted(data_tools.list_cases(), key=lambda item: item["case_id"])
        for item in items:
            case_id = str(item["case_id"])
            item["source_text"] = data_tools.get_document_text(case_id)
            item["before"] = _before_story(case_id)
        return items

    @app.post("/run")
    async def run(req: RunRequest, request: Request) -> dict[str, Any]:
        auth = _run_auth_status(request)
        known = {case["case_id"] for case in data_tools.list_cases()}
        if req.case_id not in known:
            raise HTTPException(status_code=404, detail=f"Unknown case_id: {req.case_id}")
        max_iterations = _env_int("MAX_AGENT_ITERATIONS", 4, minimum=1, maximum=6)
        if req.max_iterations > max_iterations:
            raise HTTPException(
                status_code=400,
                detail=f"max_iterations is capped at {max_iterations} for the public demo",
            )
        if auth["run_mode"] != "real":
            return _mock_response(req, auth=auth)
        if req.include_evidence and not _env_bool("ALLOW_EVIDENCE", True):
            raise HTTPException(status_code=403, detail="Evidence retrieval is disabled for this public demo")
        await _enforce_run_rate_limit(request)
        cache_key = ("real", req.case_id, req.max_iterations, req.include_evidence)
        cached = await _get_cached_run(cache_key)
        if cached is not None:
            return cached
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
        response = _response_from_run(result, include_evidence=req.include_evidence, auth=auth)
        await _set_cached_run(cache_key, response)
        return response

    return app


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _run_access_token() -> str:
    return os.environ.get("RUN_ACCESS_TOKEN", "").strip()


def _run_auth_status(request: Request) -> dict[str, Any]:
    required = _run_access_token()
    if not required:
        return {
            "run_mode": "real",
            "token_status": "not_configured",
            "token_applied": False,
            "message": "No access token is configured; local runs are unprotected.",
        }
    supplied = _request_token(request)
    if not supplied:
        return {
            "run_mode": "mock",
            "token_status": "missing",
            "token_applied": False,
            "message": "No testing token supplied; returning a mock response without Vertex calls.",
        }
    if hmac.compare_digest(supplied, required):
        return {
            "run_mode": "real",
            "token_status": "valid",
            "token_applied": True,
            "message": "Testing token accepted; real Vertex-backed ADK run is enabled.",
        }
    return {
        "run_mode": "mock",
        "token_status": "invalid",
        "token_applied": False,
        "message": "Testing token was not accepted; returning a mock response without Vertex calls.",
    }


def _request_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    scheme, _, value = auth.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return (request.query_params.get("token") or request.query_params.get("run_token") or "").strip()


def _client_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    host = request.client.host if request.client else "unknown"
    return f"{host}|{forwarded_for[:200]}"


async def _enforce_run_rate_limit(request: Request) -> None:
    window = _env_int("RUN_RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1, maximum=3600)
    per_client = _env_int("RUN_RATE_LIMIT_PER_MINUTE", 4, minimum=0, maximum=1000)
    global_limit = _env_int("RUN_GLOBAL_RATE_LIMIT_PER_MINUTE", 8, minimum=0, maximum=1000)
    if per_client == 0 and global_limit == 0:
        return

    now = time.monotonic()
    client = _client_key(request)
    async with _RATE_LOCK:
        if len(_RUN_BUCKETS) > 2048:
            _RUN_BUCKETS.clear()
        bucket = _RUN_BUCKETS[client]
        _trim_bucket(bucket, now, window)
        _trim_bucket(_GLOBAL_BUCKET, now, window)
        if per_client and len(bucket) >= per_client:
            raise HTTPException(status_code=429, detail="Run rate limit exceeded for this client")
        if global_limit and len(_GLOBAL_BUCKET) >= global_limit:
            raise HTTPException(status_code=429, detail="Global run rate limit exceeded")
        bucket.append(now)
        _GLOBAL_BUCKET.append(now)


def _trim_bucket(bucket: deque[float], now: float, window: int) -> None:
    while bucket and now - bucket[0] > window:
        bucket.popleft()


async def _get_cached_run(key: tuple[str, str, int, bool]) -> dict[str, Any] | None:
    ttl = _env_int("RUN_CACHE_TTL_SECONDS", 3600, minimum=0)
    if ttl == 0:
        return None
    now = time.monotonic()
    async with _CACHE_LOCK:
        item = _RUN_CACHE.get(key)
        if item is None:
            return None
        created, response = item
        if now - created > ttl:
            _RUN_CACHE.pop(key, None)
            return None
        cached = deepcopy(response)
        cached.setdefault("billing", {})["cache_hit"] = True
        return cached


async def _set_cached_run(key: tuple[str, str, int, bool], response: dict[str, Any]) -> None:
    ttl = _env_int("RUN_CACHE_TTL_SECONDS", 3600, minimum=0)
    if ttl == 0:
        return
    async with _CACHE_LOCK:
        if len(_RUN_CACHE) > 128:
            _RUN_CACHE.clear()
        stored = deepcopy(response)
        stored.setdefault("billing", {})["cache_hit"] = False
        _RUN_CACHE[key] = (time.monotonic(), stored)


def _response_from_run(
    run: CaseRun,
    *,
    include_evidence: bool = True,
    auth: dict[str, Any] | None = None,
    vertex_called: bool = True,
) -> dict[str, Any]:
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
        "run_mode": (auth or {}).get("run_mode", "real"),
        "auth": auth or {
            "run_mode": "real",
            "token_status": "not_configured",
            "token_applied": False,
            "message": "No access token is configured; local runs are unprotected.",
        },
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
            "events": _public_trace_events(trace),
        },
        "billing": {"cache_hit": False},
        "vertex": {"model": MODEL_ID, "location": LOCATION, "called": vertex_called},
    }


def _mock_response(req: RunRequest, *, auth: dict[str, Any]) -> dict[str, Any]:
    run = CaseRun(case_id=req.case_id)
    if req.case_id == "CASE-003":
        draft = "\n".join([
            "[MOCK MODE - no Vertex call]",
            "Diagnosis: Rectal adenocarcinoma",
            "TNM stage: [DISCREPANCY] cT2 N0 (MRI) vs cT3 N1 (MDT) - requires clinician reconciliation",
            "Key biomarkers: [DATA GAP] Key biomarkers not documented in source",
            "Margins / nodes: [DATA GAP] Margins not documented in source",
            "Safety note: mock response shown because no valid testing token was supplied.",
        ])
        events = [
            {"author": "documentation", "type": "text", "text": "mock draft 1"},
            {"author": "qc", "type": "text", "text": "mock QC rejection: conflict not explicit"},
            {"author": "documentation", "type": "text", "text": "mock draft 2"},
            {"author": "qc", "type": "text", "text": "mock QC rejection: source labels missing"},
            {"author": "documentation", "type": "text", "text": "mock draft 3"},
            {"author": "qc", "type": "text", "text": "mock QC rejection: discrepancy wording incomplete"},
            {"author": "documentation", "type": "text", "text": draft},
            {"author": "qc", "type": "tool_call", "name": "exit_loop", "args": {}},
        ]
        qc_passed = True
    else:
        draft = "\n".join([
            "[MOCK MODE - no Vertex call]",
            f"Diagnosis: synthetic case {req.case_id}",
            "TNM stage: source-grounded summary would be generated in real mode",
            "Safety note: mock response shown because no valid testing token was supplied.",
        ])
        events = [
            {"author": "documentation", "type": "text", "text": draft},
            {"author": "qc", "type": "tool_call", "name": "exit_loop", "args": {}},
        ]
        qc_passed = True
    run.events = events
    run.state = {
        "draft": draft,
        "evidence": (
            "Mock evidence: in real mode, the evidence agent runs after QC approval and can retrieve public PDQ grounding."
            if req.include_evidence
            else ""
        ),
        "qc_passed": qc_passed,
    }
    return _response_from_run(run, include_evidence=req.include_evidence, auth=auth, vertex_called=False)


def _public_trace_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return observability metadata without raw intermediate model text or tool args."""
    public: list[dict[str, Any]] = []
    for event in events:
        item: dict[str, Any] = {
            "author": event.get("author", "agent"),
            "type": event.get("type", "event"),
        }
        if event.get("name"):
            item["name"] = event["name"]
        if event.get("type") == "text":
            item["summary"] = "generated text omitted from public trace"
            item["chars"] = len(str(event.get("text") or ""))
        elif event.get("type") == "tool_call":
            args = event.get("args")
            if isinstance(args, dict):
                item["args_keys"] = sorted(str(key) for key in args)
        public.append(item)
    return public


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
