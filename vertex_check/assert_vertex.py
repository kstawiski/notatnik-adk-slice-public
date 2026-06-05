#!/usr/bin/env python3
"""C1 — Vertex transport green-assertion (load-bearing mandatory-tech gate).

Proves the agent's reasoning genuinely runs on **Vertex AI** (`aiplatform`), not AI Studio
(`generativelanguage`) and not OpenRouter, by:
  1. capturing the *actual* outbound request URL at `BaseApiClient._build_request` — the single
     gateway for sync AND async AND streamed calls, so it is transport-agnostic (httpx/aiohttp);
  2. driving the **real ADK runtime path** `Gemini.generate_content_async(...)` (async), the
     exact method C2/C3/C6 use — via the shared `agents.model.build_gemini()` factory;
  3. fail-closed assertions: a real `:generateContent` URL whose host+path bind to the expected
     Vertex project / location / model / api-version, plus negative predicate tests.

Run:
  GOOGLE_CLOUD_PROJECT=gen-lang-client-0384080704 GOOGLE_CLOUD_LOCATION=global \
  python3 vertex_check/assert_vertex.py
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import importlib.metadata as _meta
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Make `agents` importable when run from the repo root or the file's dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.model import MODEL_ID, PROJECT, LOCATION, build_gemini  # noqa: E402

EVIDENCE = Path(__file__).resolve().parent / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)

# --- universal capture: every request URL, sync or async, before transport ------------------
_CAPTURED: list[dict] = []


def _install_capture() -> None:
    from google.genai import _api_client as _ac

    orig = _ac.BaseApiClient._build_request

    def patched(self, http_method, path, request_dict, http_options=None):  # type: ignore[no-untyped-def]
        req = orig(self, http_method, path, request_dict, http_options)
        try:
            _CAPTURED.append({"method": str(http_method), "url": str(req.url)})
        except Exception:
            pass
        return req

    _ac.BaseApiClient._build_request = patched  # type: ignore[method-assign]


def _vertex_host_ok(host: str) -> bool:
    """Robust, non-spoofable: regional/global/multi-regional/mTLS Vertex, never AI Studio/look-alikes."""
    host = (host or "").lower()
    return "aiplatform" in host and host.endswith(".googleapis.com") and "generativelanguage" not in host


def _versions() -> dict:
    def v(pkg):
        try:
            return _meta.version(pkg)
        except Exception:
            return "absent"

    return {
        "python": sys.version.split()[0],
        "google-genai": v("google-genai"),
        "google-adk": v("google-adk"),
        "google-cloud-aiplatform": v("google-cloud-aiplatform"),
        "httpx": v("httpx"),
        "aiohttp": v("aiohttp"),  # if present, async path may use aiohttp — capture still works
    }


def _principal() -> dict:
    info = {}
    try:
        import google.auth

        creds, adc_project = google.auth.default()
        info["creds_class"] = type(creds).__name__
        info["adc_project"] = adc_project
        info["quota_project"] = getattr(creds, "quota_project_id", None)
        for attr in ("service_account_email", "signer_email"):
            if getattr(creds, attr, None):
                info["service_account"] = getattr(creds, attr)
        acct = getattr(creds, "account", None)
        if acct:
            info["user_account"] = acct
    except Exception as e:  # pragma: no cover
        info["error"] = f"{type(e).__name__}: {e}"
    return info


async def _run_adk_async(adk_model) -> tuple[str, int]:
    """Drive the literal runtime method ADK agents use (async)."""
    from google.adk.models.llm_request import LlmRequest
    from google.genai import types

    req = LlmRequest(
        model=MODEL_ID,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text="Reply with the single word: VERTEX")])],
        config=types.GenerateContentConfig(temperature=0),
    )
    texts = []
    chunks = 0
    async for chunk in adk_model.generate_content_async(req):
        chunks += 1
        t = getattr(chunk, "text", None)
        if not t:
            content = getattr(chunk, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if parts:
                t = "".join(p.text for p in parts if getattr(p, "text", None))
        if t:
            texts.append(t)
    return "".join(texts).strip(), chunks


def main() -> int:
    _install_capture()
    adk_model = build_gemini()  # the SAME model factory C2/C3/C6 use
    client = adk_model.api_client
    cfg_base = getattr(getattr(client, "_api_client", None), "_http_options", None)
    cfg_base_url = getattr(cfg_base, "base_url", None) if cfg_base else getattr(client, "_http_options", None)
    cfg_base_url = getattr(cfg_base_url, "base_url", cfg_base_url) if not isinstance(cfg_base_url, str) else cfg_base_url

    response_text, chunks_received = asyncio.run(_run_adk_async(adk_model))

    gen = [c for c in _CAPTURED if "generatecontent" in c["url"].lower()]
    target = gen[-1]["url"] if gen else ""
    host = urlparse(target).hostname or ""
    path = urlparse(target).path or ""

    expected_path = f"/projects/{PROJECT}/locations/{LOCATION}/publishers/google/models/{MODEL_ID}:generateContent"
    checks = {
        "async_generate_captured": bool(gen),
        "host_is_vertex": _vertex_host_ok(host),
        "host_not_ai_studio": "generativelanguage" not in host,
        "path_binds_project_location_model": expected_path in path,
        "client_is_vertexai": getattr(client, "vertexai", None) is True,
        "config_base_url_is_vertex": isinstance(cfg_base_url, str)
        and cfg_base_url.startswith("https://")
        and _vertex_host_ok(urlparse(cfg_base_url).hostname or ""),
        "got_vertex_response": chunks_received > 0 and "VERTEX" in response_text.upper(),
        # negative tests — these MUST be rejected by the predicate
        "neg_ai_studio_rejected": not _vertex_host_ok("generativelanguage.googleapis.com"),
        "neg_openrouter_rejected": not _vertex_host_ok("openrouter.ai"),
        "neg_lookalike_rejected": not _vertex_host_ok("aiplatform.evil-googleapis.com"),
    }
    green = all(checks.values())

    result = {
        "utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "project": PROJECT,
        "location": LOCATION,
        "model_requested": MODEL_ID,
        "runtime_path": "ADK Gemini.generate_content_async (async)",
        "principal": _principal(),
        "versions": _versions(),
        "client_vertexai": getattr(client, "vertexai", None),
        "client_configured_base_url": cfg_base_url,
        "response_text": response_text[:40],
        "chunks_received": chunks_received,
        "asserted_host": host,
        "asserted_path": path,
        "expected_path": expected_path,
        "captured": _CAPTURED,
        "checks": checks,
        "VERDICT": "GREEN" if green else "RED",
    }
    out = EVIDENCE / "c1_vertex_assertion.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\n{'GREEN' if green else 'RED'} — evidence: {out}")
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
