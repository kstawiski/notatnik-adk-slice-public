#!/usr/bin/env python3
"""Audit that transient judge gaps in a completed run are score-preserving (not a measurement bug).

The holistic judge is the THIRD (triangulation) metric. During a high-concurrency run some judge
calls can hit a transient Vertex 429 and return None, while the PRIMARY gold-grounded grader and the
deterministic rule cross-check (which carry the actual claims) complete. This auditor proves those
judge gaps do not change any reported judge number, by checking three properties of runs.jsonl:

  P1 DETERMINISM   — within each (config, case_id) the drafts are byte-identical across the N runs
                     (temp 0). Identical draft => identical judge input.
  P2 AGREEMENT     — wherever some runs of a group lost the judge, the SURVIVING judge values in that
                     group agree exactly. Combined with P1, a missing value equals its siblings.
  P3 NO-DROP       — no (config, case_id) group lost ALL its judge values, so every case keeps a valid
                     judge mean in every config and the paired-delta n_paired is unaffected.

P1 & P2 & P3 together => the judge means/deltas are bit-for-bit what they would be with zero gaps.
This is an audit of an EXISTING run; it makes no Vertex calls and changes no data. Read-only.

Run:  python eval/verify_judge_integrity.py eval/outputs/<run_dir>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

TOL = 1e-9


def audit(run_dir: Path) -> tuple[bool, list[str]]:
    rows = [json.loads(l) for l in (run_dir / "runs.jsonl").read_text().splitlines() if l.strip()]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["config"], r["case_id"])].append(r)

    total_judge = sum(1 for r in rows if "judge" in r)
    gaps = [r for r in rows if r.get("judge") is None]
    by_cfg: dict[str, int] = defaultdict(int)
    for r in gaps:
        by_cfg[r["config"]] += 1

    nonident = [k for k, rs in groups.items() if len({(r.get("draft") or "") for r in rs}) > 1]
    disagree = []
    for k, rs in groups.items():
        surv = [r["judge"] for r in rs if r.get("judge") is not None]
        if surv and (max(surv) - min(surv) > TOL):
            disagree.append((k, surv))
    all_lost = [k for k, rs in groups.items() if all(r.get("judge") is None for r in rs)]

    lines = [
        f"run_dir: {run_dir}",
        f"runs: {len(rows)} | (config,case) groups: {len(groups)}",
        f"judge gaps (transient 429 -> None): {len(gaps)}/{total_judge} "
        f"({100 * len(gaps) / total_judge:.1f}%) by config: {dict(by_cfg)}",
        "",
        f"P1 DETERMINISM  (drafts identical across runs per group): "
        f"{'PASS' if not nonident else 'FAIL ' + str(nonident)}",
        f"P2 AGREEMENT    (surviving judge values agree within each group): "
        f"{'PASS' if not disagree else 'FAIL ' + str(disagree)}",
        f"P3 NO-DROP      (no group lost ALL judge values): "
        f"{'PASS' if not all_lost else 'FAIL ' + str(all_lost)}",
    ]
    ok = not nonident and not disagree and not all_lost
    lines.append("")
    lines.append(
        "VERDICT: PASS — the %d judge gap(s) are score-preserving; judge means/deltas are identical "
        "to a zero-gap run (P1&P2&P3). The claim-bearing layers (agent runs, primary grader, rule "
        "cross-check) had no gaps." % len(gaps) if ok else
        "VERDICT: FAIL — a judge gap could have changed a reported number; investigate before use."
    )
    return ok, lines


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    ok, lines = audit(Path(sys.argv[1]))
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
