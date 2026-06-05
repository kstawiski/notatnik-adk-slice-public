"""Canonical Gemini-on-Vertex model factory.

C1 (`vertex_check/assert_vertex.py`) verifies the model built HERE. C2/C3/C6 must construct the
runtime model via `build_gemini()` so the Vertex-transport proof transfers to the agent that
actually runs. Do not construct `Gemini(...)` ad hoc elsewhere — import this.
"""
from __future__ import annotations

import os

# Pinned for reproducibility (C1 evidence + C4 eval). The resolved server-side model version is
# recorded in C1 evidence; bump deliberately, never via a moving "-latest" alias.
MODEL_ID = "gemini-3.1-flash-lite"
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0384080704")
# Gemini 3.x is served from the Vertex **global** endpoint only (it 404s in us-central1).
# text-embedding-005 also resolves on global and is location-independent (identical vectors),
# so the committed C5 index — built in us-central1 — stays valid when queried from global.
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")


def ensure_vertex_env() -> None:
    """Force the google-genai SDK onto the Vertex backend (not AI Studio), pinned to LOCATION."""
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT)
    # Force (not setdefault): the ADK agent reads GOOGLE_CLOUD_LOCATION from env, and the gen
    # model only exists on `global` — a stale us-central1 in the environment would 404.
    os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"


def build_gemini():
    """The single source of truth for the agent's reasoning model (Gemini via Vertex)."""
    ensure_vertex_env()
    from google.adk.models.google_llm import Gemini

    return Gemini(model=MODEL_ID)
