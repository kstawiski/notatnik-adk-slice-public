"""C3 — ADK multi-agent reliability slice.

A deterministic workflow orchestrator (chosen over LLM-driven transfer so the C4 eval is
reproducible) wiring three LLM sub-agents that reason on Gemini via Vertex AI (the shared
C1 `build_gemini()` client) and consume the C2 tools over a REAL ADK MCP toolset (stdio ->
`mcp_server/server.py`):

    orchestrator (SequentialAgent)
      |- review_loop (LoopAgent, max_iterations=N)
      |    |- documentation (LlmAgent)  -> drafts a structured summary, state['draft']
      |    |- qc           (LlmAgent)   -> independently re-reads source (include_contents='none'),
      |    |                               audits draft; exit_loop+qc_passed on pass, else qc_feedback
      |- evidence (LlmAgent)            -> citations for the QC-passed summary; WITHHELD if QC
                                          never passed (before_agent_callback gates on qc_passed)

Reliability story: QC halts on an injected error (missing TNM / contradiction) by NOT
calling exit_loop, the loop re-runs documentation with the feedback, and the draft
self-corrects. A draft QC never approves does not receive evidence. Prompts are
sanitized/non-proprietary (prompts/sanitized.py).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from mcp import StdioServerParameters

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from agents.model import build_gemini  # noqa: E402
from prompts import sanitized  # noqa: E402
from tools import data_tools  # noqa: E402
from tools.safety import scrub_mapping  # noqa: E402

APP_NAME = "notatnik-adk-slice"
MCP_SERVER = _ROOT / "mcp_server" / "server.py"
ALL_TOOLS = ["get_document_text", "list_cases", "search_pubmed", "search_trials", "retrieve_guideline"]


def build_mcp_toolset() -> McpToolset:
    """A genuine ADK MCP toolset (stdio client) bound to the C2 MCP server.

    The stdio subprocess is given this process's environment (MOCK_MODE, GROUNDING_PDQ,
    GOOGLE_CLOUD_* and ADC via HOME) so the DATA tools run with the same Vertex config as the
    agents — in particular retrieve_guideline's PDQ embeddings grounding needs Vertex in-process.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable, args=[str(MCP_SERVER)], env=dict(os.environ)
            ),
            timeout=30.0,
        )
    )


def exit_loop(tool_context: ToolContext) -> dict:
    """Signal that the draft passed QC; stops the review loop. Call ONLY on a clean pass."""
    tool_context.actions.escalate = True
    tool_context.state["qc_passed"] = True  # authoritative pass flag (gates the evidence step)
    return {"status": "qc_passed"}


_EVIDENCE_WITHHELD = (
    "[QC_UNRESOLVED] evidence withheld — QC did not approve the summary within max_iterations"
)


def _gate_evidence(callback_context) -> types.Content | None:
    """Do not retrieve evidence for a draft QC never approved (returning content skips the agent)."""
    if not callback_context.state.get("qc_passed"):
        callback_context.state["evidence"] = _EVIDENCE_WITHHELD
        return types.Content(role="model", parts=[types.Part.from_text(text=_EVIDENCE_WITHHELD)])
    return None


def _temp0() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(temperature=0)


def _documentation_agent(model, toolset, instruction: str) -> LlmAgent:
    return LlmAgent(
        name="documentation",
        model=model,
        instruction=instruction,
        tools=[toolset],
        generate_content_config=_temp0(),
        output_key="draft",
    )


def build_graph(
    toolset: McpToolset,
    max_iterations: int = 4,
    *,
    documentation_instruction: str = sanitized.DOCUMENTATION_INSTRUCTION,
    qc_instruction: str = sanitized.QC_INSTRUCTION,
    evidence_instruction: str = sanitized.EVIDENCE_INSTRUCTION,
    include_evidence: bool = True,
) -> SequentialAgent:
    """Construct the multi-agent graph over an already-created toolset (caller owns its lifecycle).

    The instructions are parameters so the C4 eval can compare baseline vs optimized prompts on
    the IDENTICAL graph; the defaults are the sanitized C3 prompts (unchanged default behaviour).

    `include_evidence` (default True = full product graph). The C4 reliability eval sets it FALSE:
    it scores the QC-finalized `draft`, and the downstream evidence agent runs AFTER the draft is
    set and does not change it — so including it only adds a post-draft failure surface (an evidence
    Vertex error would mark the whole run failed and bias n_failed / optimizer selection / deltas)
    and wasted compute. Grounding/citations are exercised separately (C5).
    """
    model = build_gemini()
    documentation = _documentation_agent(model, toolset, documentation_instruction)
    qc = LlmAgent(
        name="qc",
        model=model,
        instruction=qc_instruction,
        tools=[toolset, exit_loop],
        generate_content_config=_temp0(),
        # 'none' forces QC to fetch the source itself (independent audit) rather than relying
        # on the documentation agent's tool response sitting in shared history.
        include_contents="none",
        output_key="qc_feedback",
    )
    review_loop = LoopAgent(name="review_loop", sub_agents=[documentation, qc], max_iterations=max_iterations)
    if not include_evidence:
        return SequentialAgent(name="orchestrator", sub_agents=[review_loop])
    evidence = LlmAgent(
        name="evidence",
        model=model,
        instruction=evidence_instruction,
        tools=[toolset],
        generate_content_config=_temp0(),
        before_agent_callback=_gate_evidence,  # withhold evidence unless QC approved the draft
        output_key="evidence",
    )
    return SequentialAgent(name="orchestrator", sub_agents=[review_loop, evidence])


def build_single_agent(
    toolset: McpToolset, *, documentation_instruction: str = sanitized.DOCUMENTATION_INSTRUCTION
) -> LlmAgent:
    """The single-agent baseline: documentation only, no QC loop, no evidence (the C4 'before')."""
    return _documentation_agent(build_gemini(), toolset, documentation_instruction)


def build_orchestrator(max_iterations: int = 4) -> tuple[SequentialAgent, McpToolset]:
    """Convenience: build a toolset + graph together. Caller must close the toolset."""
    toolset = build_mcp_toolset()
    return build_graph(toolset, max_iterations), toolset


# ---------------------------------------------------------------------------- run + trace

@dataclass
class CaseRun:
    case_id: str
    events: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)

    @property
    def doc_drafts(self) -> int:
        # The LoopAgent runs [documentation, qc] per iteration and only advances to the next
        # documentation turn when QC did NOT escalate. So the draft count IS the iteration
        # count — a purely structural signal, independent of QC's text formatting.
        return sum(1 for e in self.events if e["author"] == "documentation" and e["type"] == "text")

    @property
    def qc_passed(self) -> bool:
        # Authoritative: set by the exit_loop tool in session state (not inferred from text).
        return bool(self.state.get("qc_passed"))

    @property
    def qc_rejections(self) -> int:
        # Every draft except the QC-approved final one was a rejected draft.
        return self.doc_drafts - 1 if self.qc_passed else self.doc_drafts

    @property
    def self_corrected(self) -> bool:
        # >=2 drafts means QC rejected an earlier draft; a pass means the redo was accepted.
        return self.doc_drafts >= 2 and self.qc_passed

    @property
    def qc_feedback_log(self) -> list[str]:
        # Display-only (not used by any metric): the QC defect lists, in order.
        return [e["text"] for e in self.events if e["author"] == "qc" and e["type"] == "text"]

    def tool_calls(self) -> list[str]:
        return [e["name"] for e in self.events if e["type"] == "tool_call"]


async def run_root(root, toolset: McpToolset, case_id: str, *, scrub_output: bool = False) -> CaseRun:
    """Run an already-built root agent over a case on Vertex; capture a structured trace.

    Caller owns the toolset lifecycle (closes it). Used by run_case and by the C4 harness so
    single-agent and multi-agent / baseline vs optimized configs share one runner path.
    """
    runner = InMemoryRunner(agent=root, app_name=APP_NAME)
    run = CaseRun(case_id=case_id)
    try:
        session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id="judge",
            state={"case_id": case_id, "qc_feedback": "", "qc_passed": False},
        )
        message = types.Content(role="user", parts=[types.Part.from_text(text=f"Process case {case_id}.")])
        async for event in runner.run_async(user_id="judge", session_id=session.id, new_message=message):
            _record(run, event)
        final = await runner.session_service.get_session(
            app_name=APP_NAME, user_id="judge", session_id=session.id
        )
        if final is not None:
            run.state = {k: final.state.get(k) for k in ("draft", "qc_feedback", "qc_passed", "evidence")}
        if scrub_output:
            _scrub_run(run)
    finally:
        await runner.close()
    return run


async def run_case(
    case_id: str,
    max_iterations: int = 4,
    *,
    scrub_output: bool = True,
    include_evidence: bool = True,
) -> CaseRun:
    """Run one case end-to-end on Vertex (multi-agent default); capture a structured trace."""
    # Build the toolset first so it is always closed in finally, even if graph/runner
    # construction raises (no leaked stdio subprocess).
    toolset = build_mcp_toolset()
    try:
        return await run_root(
            build_graph(toolset, max_iterations=max_iterations, include_evidence=include_evidence),
            toolset,
            case_id,
            scrub_output=scrub_output,
        )
    finally:
        await toolset.close()


def _scrub_run(run: CaseRun) -> None:
    """Redact source identifiers from final state and the display/API trace."""
    source = data_tools.get_document_text(run.case_id)
    run.state = scrub_mapping(run.state, source)
    run.events = [scrub_mapping(event, source) for event in run.events]


def _record(run: CaseRun, event) -> None:
    author = getattr(event, "author", "?")
    for call in event.get_function_calls() or []:
        run.events.append({"author": author, "type": "tool_call", "name": call.name, "args": dict(call.args or {})})
    for resp in event.get_function_responses() or []:
        run.events.append({"author": author, "type": "tool_response", "name": resp.name})
    text = _text_of(event)
    if text:
        run.events.append({"author": author, "type": "text", "text": text})


def _text_of(event) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return ""
    # Exclude thought/reasoning parts so they never leak into draft/evidence or inflate counts.
    return "".join(
        p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)
    ).strip()
