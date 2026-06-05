"""C4 rubric judge — a pinned-model qualitative score (the "rest" beyond the rule-based scorers).

A single Vertex Gemini call (pinned MODEL_ID, temperature 0) grades a summary on a sanitized,
generic reliability rubric and returns a float in [0, 1]. Pinned model + temp 0 keeps it as
reproducible as a model judge can be; the harness still records per-run values so spread is
visible. The rubric is generic/non-proprietary and distinct from production clinical rubrics.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.model import LOCATION, MODEL_ID, PROJECT, ensure_vertex_env  # noqa: E402

_RUBRIC = """\
You are grading a clinical-documentation summary for RELIABILITY against the source of truth.

SOURCE (ground truth):
{source}

SUMMARY TO GRADE:
{draft}

Score 0.0 to 1.0, weighting these equally:
- Faithful: every stated value appears in the source; nothing fabricated.
- Complete: relevant documented facts captured; fields absent from the source are explicitly
  marked as data gaps, not omitted or invented.
- Conflicts surfaced: conflicting values across the source are explicitly flagged, not
  silently resolved to one side.
- De-identified: no patient names or identifiers copied into the summary.
- Clear and concise.

Respond with ONLY a JSON object: {{"score": <number between 0.0 and 1.0>}}. No other text.
"""


def _parse(text: str) -> float | None:
    """Parse the strict-JSON score. Structured output removes the regex ambiguity of free-text
    numbers (a leading list marker '1.' vs a trailing '/1.0' have no single correct first/last rule)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        if t.lstrip().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        score = json.loads(t[start:end + 1]).get("score")
        return None if score is None else max(0.0, min(1.0, float(score)))
    except (ValueError, TypeError):
        return None


_CLIENT = None


def _client():
    """Single module-level Vertex client, created once and reused (see eval/llm_grader._client):
    avoids per-call socket/TLS churn over the run and the temporary-client GC-mid-request close;
    the google-genai sync client is safe to share across the to_thread workers."""
    global _CLIENT
    if _CLIENT is None:
        ensure_vertex_env()
        from google import genai
        _CLIENT = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    return _CLIENT


def _judge_sync(draft: str, source: str) -> str:
    from google.genai import types
    client = _client()
    resp = client.models.generate_content(
        model=MODEL_ID,
        contents=_RUBRIC.format(source=source, draft=draft),
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
    )
    return getattr(resp, "text", "") or ""


async def judge_score(draft: str, source: str, sem=None) -> float | None:
    """Pinned-model rubric score in [0, 1], or None if the model output cannot be parsed.

    Uses the sync client in a worker thread: the async client's httpx is closed when a
    temporary Client is garbage-collected mid-await, which breaks concurrent judging. When a
    semaphore is supplied the call is bounded by it, so the scoring burst cannot exceed the
    Vertex concurrency budget (otherwise hundreds of judge calls fire at once -> 429s -> silent
    None judge metrics).
    """
    if sem is not None:
        async with sem:
            return _parse(await asyncio.to_thread(_judge_sync, draft, source))
    return _parse(await asyncio.to_thread(_judge_sync, draft, source))
