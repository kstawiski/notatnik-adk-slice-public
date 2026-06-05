"""Deterministic DATA tool layer (the public MCP data boundary).

These tools return only DATA — never LLM generation. In MOCK_MODE (default) they serve the
synthetic fixtures, so the judged Cloud Run artifact is fully self-contained (no private
database, private search service, or GPU). The same function signatures back the MCP server (`mcp_server/server.py`) and the ADK
agents (C3). Live PubMed/ClinicalTrials integration is an optional, off-critical-path mode
(disabled here for determinism).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import fixtures as fx

_ROOT = Path(__file__).resolve().parents[1]


def mock_mode() -> bool:
    return os.environ.get("MOCK_MODE", "true").lower() not in ("0", "false", "no")


def _pdq_grounding_enabled() -> bool:
    """Real NCI PDQ grounding is independent of MOCK_MODE (patient data stays synthetic while
    guidelines are real, redistributable, public-domain). Explicit GROUNDING_PDQ wins; otherwise
    default to real grounding whenever not in MOCK_MODE."""
    flag = os.environ.get("GROUNDING_PDQ")
    if flag is not None:
        return flag.lower() in ("1", "true", "yes", "on")
    return not mock_mode()


def get_document_text(case_id: str) -> str:
    """Return the concatenated synthetic source-document text for a case (OCR/STT pre-extracted)."""
    case = fx.SYNTH_CASES.get(case_id)
    if not case:
        return f"NOT_FOUND: unknown case_id {case_id!r}. Known: {sorted(fx.SYNTH_CASES)}"
    parts = [f"### {d['name']}\n{d['text']}" for d in case["documents"]]
    return "\n\n".join(parts)


def list_cases() -> list[dict]:
    return [{"case_id": cid, "title": c["title"], "n_documents": len(c["documents"])}
            for cid, c in fx.SYNTH_CASES.items()]


def search_pubmed(query: str, k: int = 3) -> list[dict]:
    """Deterministic synthetic literature lookup (PubMed-shaped)."""
    if not mock_mode():
        raise NotImplementedError("Live PubMed mode is off the critical path; MOCK_MODE only.")
    return [{"pmid": r["pmid"], "title": r["title"], "journal": r["journal"], "year": r["year"],
             "snippet": r["snippet"], "url": f"https://pubmed.example/{r['pmid']}"}
            for r in fx._rank(fx._PUBMED, query, k)]


def search_trials(condition: str, k: int = 3) -> list[dict]:
    """Deterministic synthetic trial prescreen (ClinicalTrials.gov-shaped)."""
    if not mock_mode():
        raise NotImplementedError("Live ClinicalTrials mode is off the critical path; MOCK_MODE only.")
    return [{"nct_id": r["nct_id"], "title": r["title"], "phase": r["phase"], "status": r["status"],
             "snippet": r["snippet"], "url": f"https://clinicaltrials.example/{r['nct_id']}"}
            for r in fx._rank(fx._TRIALS, condition, k)]


def _stub_guidelines(query: str, k: int) -> list[dict]:
    # Synthetic-guideline path for pure MOCK_MODE (no real grounding). Same key set as the real
    # retriever path (url/score present) so downstream consumers and the C4 eval see a stable schema.
    return [{"id": r["id"], "source": r["source"], "section": r["section"],
             "text": r["text"], "url": "", "score": None,
             "citation": f"{r['source']} — {r['section']} ({r['id']})"}
            for r in fx._rank(fx.SYNTH_GUIDELINES, query, k)]


def retrieve_guideline(query: str, k: int = 3) -> list[dict]:
    """Guideline grounding for the evidence step.

    Real mode (default off-MOCK, or GROUNDING_PDQ=1): local Vertex-embeddings retrieval over the
    committed NCI PDQ corpus — self-contained (index ships in the image; up to two Vertex calls per
    query: a pinned-model disease-gate classifier, then the embed lookup only if it matches a doc),
    redistribution-safe. On a missing index or any retriever/classifier error it returns an HONEST
    MISS ([]) rather than off-topic synthetic citations — a fake citation is worse than none — so
    grounding stays honest AND can never crash the agent. The synthetic stub serves only pure
    MOCK_MODE (no real grounding).
    """
    if _pdq_grounding_enabled():
        try:
            if str(_ROOT) not in sys.path:
                sys.path.insert(0, str(_ROOT))
            from grounding import retriever

            if retriever.index_available():
                return [{"id": h["id"], "source": h["source"], "section": h["section"],
                         "text": h["snippet"], "url": h["url"], "score": h["score"],
                         "citation": f"{h['source']} — {h['section']} ({h['url']})"}
                        for h in retriever.retrieve(query, k)]
            print("[retrieve_guideline] PDQ index unavailable; honest miss ([])", file=sys.stderr)
        except Exception as e:  # graceful, visible degradation — never fatal to the agent
            print(f"[retrieve_guideline] PDQ grounding error; honest miss ([]): {e}", file=sys.stderr)
        return []  # real-grounding mode never falls back to off-topic synthetic citations
    return _stub_guidelines(query, k)


# Public tool registry (consumed by the MCP server and the ADK agents).
TOOLS = {
    "get_document_text": get_document_text,
    "list_cases": list_cases,
    "search_pubmed": search_pubmed,
    "search_trials": search_trials,
    "retrieve_guideline": retrieve_guideline,
}
