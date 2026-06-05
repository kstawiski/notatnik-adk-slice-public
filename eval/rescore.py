#!/usr/bin/env python3
"""Re-apply the deterministic rule CROSS-CHECK to a completed eval run from its saved drafts.

The agent drafts in runs.jsonl are the expensive artifact; the rule-based scorers are
deterministic, so a rule-scorer change can be applied to saved drafts without re-running agents.
The PRIMARY metric (the gold-grounded LLM grader composite) and the recorded judge values are kept
AS-IS from the original run (re-running the grader would need fresh Vertex calls). Writes
summary_rescored.json next to the input.

Run:  python eval/rescore.py eval/outputs/<run_dir>
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.model import MODEL_ID  # noqa: E402
from eval import scorers  # noqa: E402
from eval.harness import _agg, load_gold, source_of, split_cases  # noqa: E402


def main() -> int:
    run_dir = Path(sys.argv[1])
    gold = load_gold()
    _, test = split_cases(gold)

    records, config_order = [], []
    for line in (run_dir / "runs.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["config"] not in config_order:
            config_order.append(r["config"])
        if not r.get("error"):
            sc = scorers.score_case(gold[r["case_id"]], r.get("draft") or "", source_of(r["case_id"]))
            r["scores"] = sc
            r["rule_composite"] = sc.get("rule_based_composite")  # refresh the cross-check only
            # PRIMARY r["composite"] (LLM grader) and r["llm_dims"] are preserved from the original run
        records.append(r)

    summary = _agg(records, config_order, gold, test)
    summary["meta"] = {"rescored_from": str(run_dir), "n_cases": len({r["case_id"] for r in records}),
                       "test": test, "model": f"{MODEL_ID} (pinned)", "temperature": 0,
                       "no_significance_claim": "descriptive reliability profile; no significance at this n"}
    (run_dir / "summary_rescored.json").write_text(json.dumps(summary, indent=2))
    with (run_dir / "runs_rescored.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print("=== RESCORED SUMMARY (PRIMARY llm preserved; rule cross-check refreshed) ===")
    for name, s in summary["configs"].items():
        print(f"{name:26} llm={s['macro_composite']} rule={s['rule_macro_composite']} "
              f"judge={s['judge_mean']} self_corr={s['self_corrected_rate']}")
    d = summary["deltas"]
    for k, v in d.items():
        print(f"  {k}: delta={v['delta']} (n_paired={v['n_paired']})")
    print(f"\nwrote: {run_dir/'summary_rescored.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
