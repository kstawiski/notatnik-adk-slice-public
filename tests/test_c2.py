#!/usr/bin/env python3
"""C2 tests — deterministic tool layer + a REAL MCP client<->server round-trip.

PASS criteria:
  - every tool is deterministic (same input -> identical output across calls);
  - known synthetic facts are returned (e.g. CASE-002 has no documented TNM);
  - the tools are genuinely callable over MCP (stdio): list_tools shows all 5, and a call
    through the MCP client returns the same payload as the in-process function.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import data_tools as dt  # noqa: E402


def test_determinism() -> None:
    # same input -> identical output
    assert dt.get_document_text("CASE-001") == dt.get_document_text("CASE-001")
    assert dt.search_pubmed("breast er endocrine") == dt.search_pubmed("breast er endocrine")
    assert dt.search_trials("rectal") == dt.search_trials("rectal")
    assert dt.retrieve_guideline("lung tnm staging") == dt.retrieve_guideline("lung tnm staging")
    # known synthetic facts
    c2 = dt.get_document_text("CASE-002")
    assert "non-small cell" in c2.lower() and "no tnm" in c2.lower(), "CASE-002 must lack a TNM stage"
    assert "NOT_FOUND" in dt.get_document_text("NOPE")
    top = dt.search_pubmed("rectal chemoradiotherapy t3", k=1)
    assert top and top[0]["pmid"] == "SYN10003", top
    g = dt.retrieve_guideline("rectal t3 staging", k=1)
    assert g and g[0]["id"] == "SG-RE-01" and "citation" in g[0], g
    # honest miss: a query with zero keyword overlap returns nothing, never an
    # unrelated record (no off-topic clinical citations).
    assert dt.search_pubmed("melanoma uveal xyz") == [], "no-match must be empty"
    assert dt.retrieve_guideline("zzz nonexistent") == [], "no-match must be empty"
    assert dt.search_trials("zzz nonexistent") == [], "no-match must be empty"
    # negative k is clamped to 0, not interpreted as a Python negative slice.
    assert dt.search_pubmed("rectal", k=-1) == [], "negative k must clamp to empty"
    print("  determinism + known-facts: PASS")


async def _mcp_roundtrip() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            expected = sorted(["get_document_text", "list_cases", "search_pubmed", "search_trials", "retrieve_guideline"])
            assert names == expected, f"MCP tools mismatch: {names} != {expected}"

            res = await session.call_tool("get_document_text", {"case_id": "CASE-002"})
            text = "".join(getattr(c, "text", "") for c in res.content)
            assert "non-small cell" in text.lower(), f"MCP call returned unexpected: {text[:120]}"

            res2 = await session.call_tool("search_pubmed", {"query": "rectal chemoradiotherapy t3", "k": 1})
            payload = "".join(getattr(c, "text", "") for c in res2.content)
            assert "SYN10003" in payload, f"MCP pubmed unexpected: {payload[:160]}"
            # Boundary fidelity: the structured payload returned over MCP must be
            # byte-for-byte the in-process function output, not merely "contains".
            assert res2.structuredContent == {"result": dt.search_pubmed("rectal chemoradiotherapy t3", 1)}, \
                f"MCP structured payload diverged: {res2.structuredContent}"
            print(f"  MCP round-trip over stdio: PASS ({len(names)} tools: {names})")


def main() -> int:
    print("C2 tests:")
    test_determinism()
    asyncio.run(_mcp_roundtrip())
    print("\nC2 GREEN — deterministic tool layer callable over a real MCP boundary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
