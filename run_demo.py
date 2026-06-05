#!/usr/bin/env python3
"""C3 end-to-end demo runner — runs the multi-agent slice on a synthetic case on Vertex.

Prints a readable trace (per-agent turns, tool calls, QC iterations, final summary +
evidence) and optionally writes a JSON trace under agents/evidence/. Makes REAL Gemini
calls via Vertex (the C1 client). Synthetic data only.

  GOOGLE_CLOUD_PROJECT=gen-lang-client-0384080704 GOOGLE_CLOUD_LOCATION=global \\
  python run_demo.py --case CASE-002 --evidence
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.pipeline import CaseRun, run_case  # noqa: E402

EVIDENCE = ROOT / "agents" / "evidence"


def _print_trace(run: CaseRun) -> None:
    print(f"\n=== case {run.case_id} ===")
    for e in run.events:
        if e["type"] == "tool_call":
            print(f"  [{e['author']}] -> tool {e['name']}({e['args']})")
        elif e["type"] == "tool_response":
            print(f"  [{e['author']}] <- {e['name']} returned")
        else:
            head = e["text"].splitlines()[0][:100] if e["text"] else ""
            print(f"  [{e['author']}] text: {head}{'...' if len(e['text']) > 100 else ''}")
    print("\n--- derived ---")
    print(f"  documentation drafts : {run.doc_drafts}")
    print(f"  qc rejections        : {run.qc_rejections}")
    print(f"  qc passed (exit_loop): {run.qc_passed}")
    print(f"  self-corrected       : {run.self_corrected}")
    print(f"  tool calls           : {run.tool_calls()}")
    for i, fb in enumerate(run.qc_feedback_log, 1):
        print(f"\n  QC rejection #{i}:\n    " + fb.replace("\n", "\n    "))
    print("\n--- final draft ---")
    print(run.state.get("draft") or "(none)")
    print("\n--- evidence ---")
    print(run.state.get("evidence") or "(none)")


def _to_dict(run: CaseRun) -> dict:
    return {
        "case_id": run.case_id,
        "doc_drafts": run.doc_drafts,
        "qc_rejections": run.qc_rejections,
        "qc_passed": run.qc_passed,
        "self_corrected": run.self_corrected,
        "tool_calls": run.tool_calls(),
        "qc_feedback_log": run.qc_feedback_log,
        "events": run.events,
        "state": run.state,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="CASE-002", help="synthetic case id (CASE-001/002/003)")
    ap.add_argument("--max-iterations", type=int, default=4)
    ap.add_argument("--evidence", action="store_true", help="write JSON trace under agents/evidence/")
    args = ap.parse_args()

    run = asyncio.run(run_case(args.case, max_iterations=args.max_iterations))
    _print_trace(run)

    if args.evidence:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = EVIDENCE / f"c3_run_{args.case}_{stamp}.json"
        out.write_text(json.dumps(_to_dict(run), indent=2))
        print(f"\nevidence: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
