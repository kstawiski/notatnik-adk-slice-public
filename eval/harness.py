#!/usr/bin/env python3
"""C4 reliability evaluation harness.

Runs configs x cases x n on Vertex, scores each draft (rule-based + pinned judge), writes
per-run JSONL traces + an aggregate summary, and reports two before/after deltas, each
isolating ONE variable:

  Δ1 (QC-loop effect)        = multi_agent_optimized − single_agent_optimized   (same doc prompt)
  Δ2 (prompt-optimization)   = multi_agent_optimized − multi_agent_baseline     (held-out TEST)

The optimizer (scripted instruction-tuning, NOT the Vertex Prompt Optimizer service) selects
generic instruction augmentations on the TRAIN split; Δ2 is reported on the held-out TEST split.
n ≥ 3 @ temp 0; spread reported. With 15 cases NO statistical significance is claimed.

Run:  python eval/harness.py --runs 3
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.model import MODEL_ID  # noqa: E402
from agents.pipeline import CaseRun, build_graph, build_mcp_toolset, build_single_agent, run_root  # noqa: E402
from eval import judge as judgemod  # noqa: E402
from eval import llm_grader  # noqa: E402
from eval import scorers  # noqa: E402
from eval.prompts_baseline import AUGMENTATIONS, BASELINE, PromptSet, compose  # noqa: E402
from tools import data_tools  # noqa: E402

CASES_DIR = ROOT / "eval" / "cases"
OUT = ROOT / "eval" / "outputs"


def load_gold() -> dict[str, dict]:
    gold = {}
    for line in (CASES_DIR / "gold.jsonl").read_text().splitlines():
        if line.strip():
            g = json.loads(line)
            gold[g["case_id"]] = g
    return gold


def split_cases(gold: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Deterministic, stratified train/test split. Single-member categories go to TEST."""
    by_cat: dict[str, list[str]] = {}
    for cid, g in gold.items():
        by_cat.setdefault(g["category"], []).append(cid)
    train, test = [], []
    for cat, ids in by_cat.items():
        ids = sorted(ids)
        if len(ids) == 1:
            test.append(ids[0])
            continue
        for i, cid in enumerate(ids):
            (train if i % 2 == 0 else test).append(cid)
    return sorted(train), sorted(test)


def source_of(case_id: str) -> str:
    return data_tools.get_document_text(case_id)


@dataclass
class Config:
    name: str
    single: bool
    prompts: PromptSet


async def _run_one(cfg: Config, case_id: str, sem: asyncio.Semaphore):
    async with sem:
        toolset = build_mcp_toolset()
        try:
            if cfg.single:
                root = build_single_agent(toolset, documentation_instruction=cfg.prompts.documentation)
            else:
                # include_evidence=False: C4 scores the QC-finalized draft; the downstream evidence
                # agent doesn't change it and would only add a post-draft failure surface that biases
                # n_failed / optimizer selection / deltas.
                root = build_graph(toolset, documentation_instruction=cfg.prompts.documentation,
                                   qc_instruction=cfg.prompts.qc, include_evidence=False)
            return await run_root(root, toolset, case_id)
        finally:
            await toolset.close()


async def _safe_run(cfg: Config, case_id: str, sem: asyncio.Semaphore, attempts: int = 3):
    """Retry transient failures (FUSE ENOTCONN, Vertex 429) so one hiccup never aborts the run."""
    last = None
    for i in range(attempts):
        try:
            return await _run_one(cfg, case_id, sem)
        except Exception as e:  # noqa: BLE001 — eval must be resilient across hundreds of runs
            last = e
            await asyncio.sleep(1.5 * (i + 1))
    print(f"  RUN FAILED {cfg.name}/{case_id}: {type(last).__name__}: {last}", file=sys.stderr)
    r = CaseRun(case_id=case_id)
    r.state = {"_error": f"{type(last).__name__}: {last}"}
    return r


async def _score(run, gold: dict, source: str, use_judge: bool, sem: asyncio.Semaphore) -> dict:
    """PRIMARY score = gold-grounded LLM grader (composite); rule scorers kept as a cross-check.
    Grader + judge are bounded by `sem` so the scoring burst respects the Vertex concurrency budget."""
    if run.state.get("_error"):
        return {"scores": {}, "llm_dims": {}, "rule_composite": None, "composite": None, "judge": None,
                "error": run.state["_error"], "qc_passed": False, "self_corrected": False,
                "doc_drafts": 0, "qc_rejections": 0, "draft": ""}
    draft = run.state.get("draft") or ""
    rule = scorers.score_case(gold, draft, source)            # deterministic auditable cross-check
    graded = await llm_grader.grade(draft, source, gold, sem)  # PRIMARY (gold-grounded LLM grader)
    j = None
    if use_judge:
        try:
            j = await judgemod.judge_score(draft, source, sem)
        except Exception as e:  # judge is best-effort; never fail the run on it
            j = None
            print(f"  (judge error on {gold['case_id']}: {type(e).__name__})", file=sys.stderr)
    rec = {"scores": rule, "rule_composite": rule.get("rule_based_composite"),
           "llm_dims": graded["dims"], "llm_rationale": graded.get("rationale", ""),
           "composite": graded["llm_composite"], "judge": j,
           "qc_passed": run.qc_passed, "self_corrected": run.self_corrected,
           "doc_drafts": run.doc_drafts, "qc_rejections": run.qc_rejections, "draft": draft}
    if graded.get("error"):
        rec["grade_error"] = graded["error"]
    return rec


async def _mean_composite(prompts: PromptSet, cases: list[str], gold: dict, sem) -> float | None:
    """Mean rule-based composite for a multi-agent config over cases (n=1; optimizer-internal).

    A crashed run counts as 0.0 (a reliability failure that the augmentation should be penalized
    for) so every candidate is averaged over the SAME denominator (all train cases) and is directly
    comparable. Returns None only if NO case produced a successful run — a total failure (e.g. a
    transient Vertex outage), which the caller must distinguish from a genuine 0.0."""
    cfg = Config("probe", single=False, prompts=prompts)
    runs = await asyncio.gather(*(_safe_run(cfg, c, sem) for c in cases))
    vals, n_ok = [], 0
    for c, r in zip(cases, runs):
        if r.state.get("_error"):
            vals.append(0.0)  # crashed run = reliability failure; keep the common denominator
            continue
        s = scorers.score_case(gold[c], r.state.get("draft") or "", source_of(c))
        comp = s["rule_based_composite"]
        vals.append(comp if comp is not None else 0.0)
        n_ok += 1
    if n_ok == 0:
        return None  # total failure, not a genuine 0.0
    return sum(vals) / len(vals)


async def optimize(train: list[str], gold: dict, sem) -> dict:
    """Scripted instruction-tuning by FORWARD-GREEDY selection on the TRAIN split.

    Each round, evaluate adding each not-yet-selected augmentation on top of the current set and
    add the one with the best train-composite gain; stop when none improves. Forward selection
    (vs per-augmentation) captures interactions (e.g. 'never fabricate' can suppress a gap
    acknowledgement unless the explicit data-gap rule is also present), so the optimized set
    never scores below baseline on train.
    """
    base = await _mean_composite(BASELINE, train, gold, sem)
    if base is None:  # total train failure (e.g. Vertex outage) — do NOT silently select nothing
        print("WARNING: optimizer baseline probe TOTALLY FAILED (no successful train run); "
              "falling back to all-augmentations (no train search).", file=sys.stderr)
        return {"baseline_train_composite": None, "optimized_train_composite": None,
                "selected": [a["name"] for a in AUGMENTATIONS], "rounds": [],
                "method": "all-augmentations (optimizer aborted: train total-failure)"}
    selected: list[str] = []
    rounds: list[dict] = []
    remaining = [a["name"] for a in AUGMENTATIONS]
    current = base
    while remaining:
        trials = await asyncio.gather(
            *(_mean_composite(compose(selected + [name]), train, gold, sem) for name in remaining)
        )
        # a None trial is a total failure, not a win: sort it to the bottom (-1.0) so an outage
        # can never spuriously beat a real composite
        scored = sorted(zip(remaining, trials), key=lambda t: t[1] if t[1] is not None else -1.0, reverse=True)
        best_name, best_comp = scored[0]
        rounds.append({"with": selected + [best_name],
                       "composite": round(best_comp, 4) if best_comp is not None else None,
                       "candidates": {n: (round(c, 4) if c is not None else None) for n, c in scored}})
        if best_comp is None:
            print("WARNING: optimizer round produced no valid trial composite; stopping early.", file=sys.stderr)
            break
        if best_comp <= current + 1e-9:
            break
        selected.append(best_name)
        remaining.remove(best_name)
        current = best_comp
    return {"baseline_train_composite": round(base, 4), "optimized_train_composite": round(current, 4),
            "selected": selected, "rounds": rounds,
            "method": "scripted forward-greedy instruction-tuning on held-in train split"}


def _agg(records: list[dict], configs: list[str], gold: dict, test: list[str]) -> dict:
    """Aggregate per-config means and contrasts. PRIMARY metric = the gold-grounded LLM grader
    composite (`composite`); the deterministic rule composite is reported as an auditable cross-check.
    Deltas are PAIRED — computed over cases with a valid PRIMARY score in BOTH configs (n_paired)."""
    rule_dims = list(scorers.RULE_SCORERS.keys())
    llm_dims_all = ["diagnosis_present", "gap_flagged", "no_fabricated_stage",
                    "contradiction_surfaced", "faithfulness", "no_pii_leak"]

    def per_case_composite(cfg: str, cases: list[str], field: str = "composite") -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for r in records:
            if r["config"] == cfg and r["case_id"] in cases and r.get(field) is not None:
                out.setdefault(r["case_id"], []).append(r[field])
        return out

    all_cases = sorted(gold)
    summary = {"configs": {}}
    for cfg in configs:
        pcc = per_case_composite(cfg, all_cases)
        case_means = {c: statistics.mean(v) for c, v in pcc.items()}
        macro = round(statistics.mean(case_means.values()), 4) if case_means else None
        stab = round(statistics.mean([statistics.pstdev(v) for v in pcc.values() if len(v) > 1]) or 0.0, 4) \
            if any(len(v) > 1 for v in pcc.values()) else 0.0

        def _dim_means(field: str, dimlist: list[str]) -> dict:
            # case-macro (mean per case, then mean of case means) to MATCH the headline macro_composite
            # and the paired deltas, so uneven failure/run counts cannot reweight the per-dimension
            # reports differently from the composite they should reconcile with.
            dm = {}
            for d in dimlist:
                by_case: dict[str, list[float]] = {}
                for r in records:
                    if r["config"] == cfg and (r.get(field) or {}).get(d) is not None:
                        by_case.setdefault(r["case_id"], []).append(r[field][d])
                cms = [statistics.mean(vs) for vs in by_case.values()]
                dm[d] = round(statistics.mean(cms), 4) if cms else None
            return dm

        def _macro_record(valfn) -> float | None:
            # case-macro a per-record scalar (mean per case, then over cases) so the cross-check and
            # judge aggregates reconcile with the case-macro headline composite and the paired deltas.
            by_case: dict[str, list[float]] = {}
            for r in records:
                if r["config"] == cfg:
                    v = valfn(r)
                    if v is not None:
                        by_case.setdefault(r["case_id"], []).append(v)
            cms = [statistics.mean(vs) for vs in by_case.values()]
            return round(statistics.mean(cms), 4) if cms else None

        def _absdiff(r):
            return (abs(r["composite"] - r["rule_composite"])
                    if r.get("composite") is not None and r.get("rule_composite") is not None else None)

        sc = [r["self_corrected"] for r in records if r["config"] == cfg]
        n_total = sum(1 for r in records if r["config"] == cfg)
        n_failed = sum(1 for r in records if r["config"] == cfg and r.get("composite") is None)
        summary["configs"][cfg] = {
            "macro_composite": macro,                                   # PRIMARY (LLM grader)
            "per_dimension_llm": _dim_means("llm_dims", llm_dims_all),  # PRIMARY
            "rule_macro_composite": _macro_record(lambda r: r.get("rule_composite")),   # cross-check (case-macro)
            "per_dimension_rule": _dim_means("scores", rule_dims),                       # cross-check
            "llm_vs_rule_mean_abs_diff": _macro_record(_absdiff),
            "judge_mean": _macro_record(lambda r: r.get("judge")),
            "self_corrected_rate": round(sum(sc) / len(sc), 4) if sc else None,
            "mean_run_to_run_stdev": stab,
            "n_cases": len(case_means),
            "n_runs": n_total,
            "n_failed": n_failed,
        }

    def delta(cfg_a: str, cfg_b: str, cases: list[str], field: str = "composite") -> dict:
        """Paired contrast a-b over cases with a valid score (in `field`) in BOTH configs. Also
        reports the DIRECTION distribution (cases improved / regressed / tied) — a descriptive,
        sign-level summary of consistency with NO significance claim."""
        a, b = per_case_composite(cfg_a, cases, field), per_case_composite(cfg_b, cases, field)
        common = sorted(set(a) & set(b))
        if not common:
            return {"a": None, "b": None, "delta": None, "n_paired": 0,
                    "improved": 0, "regressed": 0, "tied": 0}
        am = {c: statistics.mean(a[c]) for c in common}
        bm = {c: statistics.mean(b[c]) for c in common}
        ma, mb = statistics.mean(am.values()), statistics.mean(bm.values())
        improved = sum(1 for c in common if am[c] > bm[c] + 1e-9)
        regressed = sum(1 for c in common if am[c] < bm[c] - 1e-9)
        return {"a": round(ma, 4), "b": round(mb, 4), "delta": round(ma - mb, 4), "n_paired": len(common),
                "improved": improved, "regressed": regressed, "tied": len(common) - improved - regressed}

    # the eight headline contrasts, defined once and computed under three metrics so the trusted
    # summary carries its OWN cross-check ON THE CLAIMS (not only per-config): the LLM-grader
    # primary, the deterministic rule composite, and the holistic judge (whose rubric is least
    # keyed to the optimized prompt's literal markers — the strongest self-preference rebuttal).
    contrasts = [
        ("qc_loop_at_baseline_all",    "multi_agent_baseline",  "single_agent_baseline", all_cases),
        ("qc_loop_at_optimized_all",   "multi_agent_optimized", "single_agent_optimized", all_cases),
        ("qc_loop_at_optimized_TEST",  "multi_agent_optimized", "single_agent_optimized", test),
        ("prompt_opt_for_multi_TEST",  "multi_agent_optimized", "multi_agent_baseline",   test),
        ("prompt_opt_for_single_TEST", "single_agent_optimized", "single_agent_baseline", test),
        ("prompt_opt_for_single_all",  "single_agent_optimized", "single_agent_baseline", all_cases),
        ("combined_worst_to_best_TEST", "multi_agent_optimized", "single_agent_baseline", test),
        ("combined_worst_to_best_all",  "multi_agent_optimized", "single_agent_baseline", all_cases),
    ]
    summary["deltas"] = {k: delta(a, b, cs) for k, a, b, cs in contrasts}                          # PRIMARY (LLM)
    summary["deltas_rule"] = {k: delta(a, b, cs, "rule_composite") for k, a, b, cs in contrasts}    # cross-check
    summary["deltas_judge"] = {k: delta(a, b, cs, "judge") for k, a, b, cs in contrasts}            # triangulation

    # per-category breakdown — shows WHERE each intervention helps (clean cases have nothing to fix,
    # so the signal lives in missing_tnm / contradiction / pii_leak / faithfulness).
    def macro_over(cfg: str, cs: list[str], field: str = "composite") -> float | None:
        cms = [statistics.mean(v) for v in per_case_composite(cfg, cs, field).values()]
        return round(statistics.mean(cms), 4) if cms else None

    def nfail_over(cfg: str, cs: list[str]) -> int:
        return sum(1 for r in records if r["config"] == cfg and r["case_id"] in cs
                   and r.get("composite") is None)

    cats = sorted({g["category"] for g in gold.values()})
    summary["per_category"] = {}
    for cat in cats:
        cs = sorted(cid for cid, g in gold.items() if g["category"] == cat)
        summary["per_category"][cat] = {
            "n_cases": len(cs),
            "macro_composite": {cfg: macro_over(cfg, cs) for cfg in configs},          # PRIMARY (LLM)
            "rule_macro_composite": {cfg: macro_over(cfg, cs, "rule_composite") for cfg in configs},
            "qc_loop_optimized": delta("multi_agent_optimized", "single_agent_optimized", cs),
            "qc_loop_baseline": delta("multi_agent_baseline", "single_agent_baseline", cs),
            "combined_worst_to_best": delta("multi_agent_optimized", "single_agent_baseline", cs),
            "n_failed": {cfg: nfail_over(cfg, cs) for cfg in configs},
        }

    summary["delta_notes"] = {
        "metric": "PRIMARY = gold-grounded LLM grader composite (eval/llm_grader.py). deltas_rule is "
                  "the deterministic cross-check and deltas_judge the holistic-judge triangulation, "
                  "computed on the SAME paired contrasts so the cross-check covers the actual claims.",
        "pairing": "each delta uses cases with a valid score (for that metric) in BOTH configs "
                   "(n_paired). Pairing removes denominator-mismatch bias; it does NOT remove "
                   "informative-missingness bias, so if failures concentrate in a weaker config a "
                   "contrast is conservatively biased toward null — n_failed is reported per config "
                   "(and per category) to make this visible.",
        "held_out": "augmentations are selected on TRAIN by the deterministic composite; *_TEST deltas "
                    "are the held-out generalization. *_all deltas include TRAIN (in-sample) — supplementary.",
        "optimizer_objective": "the optimizer selects on the MULTI-agent composite; the single-agent "
                               "prompt deltas are a TRANSFER of those prompts to the single agent, not "
                               "a single-agent-native optimization.",
        "shared_vocabulary_caveat": "the optimized prompt injects the literal markers '[DATA GAP]' and "
                                    "'surface BOTH values' that the grader rubric and rule scorer also "
                                    "key on; deltas_judge (less marker-bound) is reported to show the "
                                    "gain is not merely speaking the grader's language.",
        "test_cases": test,
    }
    return summary


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cases", default="", help="comma-separated case_id subset (default: all)")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--no-optimize", action="store_true", help="skip the train search; use all augmentations")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    gold = load_gold()
    cases = [c.strip() for c in args.cases.split(",") if c.strip()] or sorted(gold)
    train, test = split_cases(gold)
    train = [c for c in train if c in cases]
    test = [c for c in test if c in cases]
    sem = asyncio.Semaphore(args.concurrency)

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT / (f"{stamp}_{args.tag}" if args.tag else stamp)
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1) optimizer (on train) -> optimized prompts
    if args.no_optimize or not train:
        opt = {"selected": [a["name"] for a in AUGMENTATIONS], "method": "all-augmentations (no train search)",
               "baseline_train_composite": None, "per_aug_train_delta": {}}
    else:
        print(f"optimizing on {len(train)} train cases: {train}")
        opt = await optimize(train, gold, sem)
    optimized = compose(opt["selected"])
    (run_dir / "optimizer.json").write_text(json.dumps(opt, indent=2))
    print(f"optimizer selected: {opt['selected']}")

    # 2) configs — full 2x2 factorial: agent {single, multi} x prompts {baseline, optimized}
    configs = [
        Config("single_agent_baseline", single=True, prompts=BASELINE),
        Config("single_agent_optimized", single=True, prompts=optimized),
        Config("multi_agent_baseline", single=False, prompts=BASELINE),
        Config("multi_agent_optimized", single=False, prompts=optimized),
    ]

    # 3) run configs x cases x runs
    tasks, meta = [], []
    for cfg in configs:
        for c in cases:
            for ri in range(args.runs):
                tasks.append(_safe_run(cfg, c, sem))
                meta.append((cfg, c, ri))
    print(f"running {len(tasks)} agent invocations ({len(configs)} configs x {len(cases)} cases x {args.runs} runs)...")
    runs = await asyncio.gather(*tasks)

    # 4) score: PRIMARY gold-grounded LLM grader + deterministic rule cross-check + rubric judge,
    #    all bounded by the same semaphore so the scoring burst respects the Vertex concurrency budget.
    records = []
    score_tasks = [_score(r, gold[c], source_of(c), not args.no_judge, sem)
                   for r, (cfg, c, ri) in zip(runs, meta)]
    scored = await asyncio.gather(*score_tasks)
    for (cfg, c, ri), sc in zip(meta, scored):
        rec = {"config": cfg.name, "case_id": c, "category": gold[c]["category"], "run_idx": ri, **sc}
        records.append(rec)
    with (run_dir / "runs.jsonl").open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    # 5) aggregate + summary
    summary = _agg(records, [c.name for c in configs], gold, test)
    n_fail = sum(1 for r in records if r.get("composite") is None)
    summary["meta"] = {"utc": stamp, "runs_per_case": args.runs, "n_cases": len(cases),
                       "train": train, "test": test, "optimizer": opt, "failed_scores": n_fail,
                       "model": f"{MODEL_ID} (pinned)", "temperature": 0,
                       "primary_metric": "gold-grounded LLM grader composite (eval/llm_grader.py)",
                       "cross_check_metric": "deterministic rule composite (eval/scorers.py)",
                       "no_significance_claim": "n=%d cases; descriptive reliability profile only" % len(cases)}
    if n_fail:
        print(f"WARNING: {n_fail} run(s) lack a PRIMARY score (failed run or grade) and are excluded; "
              f"see per-config n_failed and runs.jsonl.")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\n=== SUMMARY (PRIMARY = LLM grader; rule = cross-check) ===")
    for name, s in summary["configs"].items():
        print(f"{name:26} llm={s['macro_composite']} rule={s['rule_macro_composite']} "
              f"judge={s['judge_mean']} self_corr={s['self_corrected_rate']} "
              f"stdev={s['mean_run_to_run_stdev']} n_fail={s['n_failed']}")
    d, dr, dj = summary["deltas"], summary["deltas_rule"], summary["deltas_judge"]

    def _show(label, key):
        v, vr, vj = d[key], dr[key], dj[key]
        print(f"{label:28} Δ_llm={v['delta']} (n={v['n_paired']})  "
              f"Δ_rule={vr['delta']}  Δ_judge={vj['delta']}")

    print("\n(Δ_llm = PRIMARY gold-grounded grader; Δ_rule + Δ_judge = cross-check / triangulation)")
    _show("QC-loop @baseline (all)", "qc_loop_at_baseline_all")
    _show("QC-loop @optimized (all)", "qc_loop_at_optimized_all")
    _show("QC-loop @optimized (TEST)", "qc_loop_at_optimized_TEST")
    _show("prompt-opt multi (TEST)", "prompt_opt_for_multi_TEST")
    _show("prompt-opt single (TEST)", "prompt_opt_for_single_TEST")
    _show("combined worst->best (TEST)", "combined_worst_to_best_TEST")

    print("\n=== PER-CATEGORY (PRIMARY composite; QC-loop @optimized Δ) ===")
    for cat, s in summary["per_category"].items():
        mc = s["macro_composite"]
        ql = s["qc_loop_optimized"]
        print(f"{cat:14} n={s['n_cases']}  "
              f"single_opt={mc.get('single_agent_optimized')} multi_opt={mc.get('multi_agent_optimized')}  "
              f"QC-loop Δ={ql['delta']} (n_paired={ql['n_paired']})")
    print(f"\noutputs: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
