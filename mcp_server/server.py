#!/usr/bin/env python3
"""Real MCP server exposing the public DATA tools (the MCP data boundary).

This is a genuine Model Context Protocol server (stdio transport), not function wrappers
labeled "MCP": the ADK slice consumes it via an MCP client/toolset (C3). It serves DATA only
(synthetic in MOCK_MODE) — never LLM generation, which stays in the ADK agents on Vertex.

Run standalone:  python mcp_server/server.py   (speaks MCP over stdio)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from tools import data_tools  # noqa: E402

mcp = FastMCP("notatnik-data-tools")


@mcp.tool()
def get_document_text(case_id: str) -> str:
    """Return concatenated synthetic source-document text (OCR/STT pre-extracted) for a case."""
    return data_tools.get_document_text(case_id)


@mcp.tool()
def list_cases() -> list[dict]:
    """List available synthetic cases (case_id, title, document count)."""
    return data_tools.list_cases()


@mcp.tool()
def search_pubmed(query: str, k: int = 3) -> list[dict]:
    """Deterministic synthetic literature search (PubMed-shaped citations)."""
    return data_tools.search_pubmed(query, k)


@mcp.tool()
def search_trials(condition: str, k: int = 3) -> list[dict]:
    """Deterministic synthetic clinical-trial prescreen (ClinicalTrials.gov-shaped)."""
    return data_tools.search_trials(condition, k)


@mcp.tool()
def retrieve_guideline(query: str, k: int = 3) -> list[dict]:
    """Guideline retrieval with citations: real NCI PDQ embeddings grounding, or synthetic stub."""
    return data_tools.retrieve_guideline(query, k)


if __name__ == "__main__":
    mcp.run()
