#!/usr/bin/env python3
"""C3 deterministic tests (NO LLM / NO Vertex cost).

PASS criteria:
  - the ADK MCP toolset, driven over stdio against the C2 server, lists all 5 tools
    (proves the agent path genuinely consumes C2 via MCP — not relabeled wrappers);
  - the multi-agent graph has the expected shape (orchestrator -> [review_loop(doc, qc),
    evidence]) with the QC self-correction loop and exit_loop tool wired, and every LLM
    agent is bound to the shared Vertex model factory.

The end-to-end Vertex run (QC halt + self-correct on a synthetic case) is exercised
separately by run_demo.py (it makes real Gemini calls) and captured under agents/evidence/.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent  # noqa: E402
from google.adk.models.google_llm import Gemini  # noqa: E402
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset  # noqa: E402

from agents import model as model_mod  # noqa: E402
from agents import pipeline  # noqa: E402


async def _list_mcp_tools() -> list[str]:
    toolset = pipeline.build_mcp_toolset()
    try:
        tools = await toolset.get_tools()
        return sorted(t.name for t in tools)
    finally:
        await toolset.close()


def test_mcp_toolset_lists_five_tools() -> None:
    names = asyncio.run(_list_mcp_tools())
    assert names == sorted(pipeline.ALL_TOOLS), f"MCP toolset tools mismatch: {names}"
    print(f"  ADK MCP toolset lists all 5 C2 tools over stdio: PASS ({names})")


def test_graph_structure() -> None:
    orchestrator, toolset = pipeline.build_orchestrator(max_iterations=3)
    try:
        assert isinstance(orchestrator, SequentialAgent) and orchestrator.name == "orchestrator"
        review_loop, evidence = orchestrator.sub_agents
        assert isinstance(review_loop, LoopAgent) and review_loop.name == "review_loop"
        assert review_loop.max_iterations == 3
        documentation, qc = review_loop.sub_agents
        assert [a.name for a in (documentation, qc)] == ["documentation", "qc"]
        assert isinstance(evidence, LlmAgent) and evidence.name == "evidence"

        # output_keys feed the loop's self-correction (draft <-> qc_feedback) and the final evidence.
        assert documentation.output_key == "draft"
        assert qc.output_key == "qc_feedback"
        assert evidence.output_key == "evidence"

        # exit_loop is the QC escape hatch; only QC may end the loop.
        assert pipeline.exit_loop in qc.tools, "qc must own the exit_loop tool"
        assert pipeline.exit_loop not in documentation.tools and pipeline.exit_loop not in evidence.tools

        # QC must audit independently (fetch source itself), not via shared history.
        assert qc.include_contents == "none", "qc must re-read source independently"
        # evidence is gated: withheld unless QC approved the draft.
        cbs = evidence.canonical_before_agent_callbacks
        assert pipeline._gate_evidence in cbs, "evidence must be gated on qc_passed"

        # every LLM agent shares the C1 Vertex model factory (gemini via Vertex).
        for a in (documentation, qc, evidence):
            assert isinstance(a.model, Gemini), f"{a.name} model is not the ADK Gemini"
            assert a.model.model == model_mod.MODEL_ID
            assert any(isinstance(t, McpToolset) for t in a.tools), f"{a.name} missing MCP toolset"
            assert a.generate_content_config.temperature == 0
        print("  multi-agent graph structure + self-correction wiring: PASS")
    finally:
        asyncio.run(toolset.close())


def main() -> int:
    print("C3 deterministic tests:")
    test_mcp_toolset_lists_five_tools()
    test_graph_structure()
    print("\nC3 wiring GREEN — real ADK MCP consumption + correct multi-agent graph.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
