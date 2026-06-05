#!/usr/bin/env python3
"""Render a completed C4 run's summary.json into a Devpost-ready Markdown report.

Pure presentation: reads the gated harness outputs (summary.json for aggregates, runs.jsonl for the
per-case TEST table) and derives reader-facing tables. No Vertex calls, no recomputation of the
primary numbers — it only reshapes saved outputs. The narrative is written to lead with the HELD-OUT
result and to disclose the two honest negatives (the QC loop's held-out PHI re-introduction and its
train-concentrated contradiction gain), per the C4 results-review.

Run:  python eval/report_table.py eval/outputs/<run_dir>            # -> stdout
      python eval/report_table.py eval/outputs/<run_dir> --out eval/outputs/<run_dir>/report.md
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

CONFIGS = ["single_agent_baseline", "single_agent_optimized", "multi_agent_baseline", "multi_agent_optimized"]
CFG_LABEL = {
    "single_agent_baseline": "single · baseline",
    "single_agent_optimized": "single · optimized",
    "multi_agent_baseline": "multi · baseline",
    "multi_agent_optimized": "multi · optimized",
}
DELTA_ROWS = [
    ("QC-loop @ baseline (all)", "qc_loop_at_baseline_all"),
    ("QC-loop @ optimized (all)", "qc_loop_at_optimized_all"),
    ("QC-loop @ optimized (TEST)", "qc_loop_at_optimized_TEST"),
    ("Prompt-opt, multi (TEST)", "prompt_opt_for_multi_TEST"),
    ("Prompt-opt, single (TEST)", "prompt_opt_for_single_TEST"),
    ("Combined worst→best (TEST)", "combined_worst_to_best_TEST"),
]
DIMS = ["diagnosis_present", "gap_flagged", "no_fabricated_stage", "contradiction_surfaced",
        "faithfulness", "no_pii_leak"]
TOL = 1e-6


def _f(x) -> str:
    return "—" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)


def _sign(x) -> str:
    if x is None:
        return "—"
    return f"+{x:.3f}" if x > 0 else f"{x:.3f}"


def _dirn(d: dict) -> str:
    if not d or d.get("n_paired", 0) == 0:
        return "—"
    return f"{d.get('improved', 0)}↑ / {d.get('regressed', 0)}↓ / {d.get('tied', 0)}="


def _percase(runs: list[dict]) -> dict:
    """case_id -> config -> {composite, judge} (mean over runs; deterministic at temp 0)."""
    out: dict[str, dict[str, dict]] = {}
    by: dict[tuple, list[dict]] = {}
    for r in runs:
        by.setdefault((r["case_id"], r["config"]), []).append(r)
    for (cid, cfg), rs in by.items():
        comps = [r["composite"] for r in rs if r.get("composite") is not None]
        judges = [r["judge"] for r in rs if r.get("judge") is not None]
        out.setdefault(cid, {})[cfg] = {
            "composite": round(statistics.mean(comps), 4) if comps else None,
            "judge": round(statistics.mean(judges), 4) if judges else None,
            "category": rs[0].get("category"),
        }
    return out


def _case_note(c: dict) -> str:
    """One-line honest note for a TEST case from its four arm composites."""
    sb, so = c.get("single_agent_baseline", {}).get("composite"), c.get("single_agent_optimized", {}).get("composite")
    mo = c.get("multi_agent_optimized", {}).get("composite")
    if None in (sb, so, mo):
        return ""
    if all(abs(v - 1.0) < TOL for v in (sb, so, mo)):
        return "all arms perfect"
    parts = []
    if so > sb + TOL:
        parts.append(f"prompt-opt fixes (+{so - sb:.3f})")
    elif so < sb - TOL:
        parts.append(f"prompt-opt regresses ({so - sb:.3f})")
    if mo < so - TOL:
        parts.append(f"**QC loop regresses ({mo - so:.3f})**")
    elif mo > so + TOL:
        parts.append(f"QC loop adds (+{mo - so:.3f})")
    else:
        parts.append("QC loop neutral")
    return "; ".join(parts)


def render(summary: dict, runs: list[dict] | None) -> str:
    # NOTE: table cells are data-driven from summary.json/runs.jsonl, but some explanatory PROSE below
    # embeds run-specific numeric literals (e.g. "+0.188", "−0.042", "0.933→1.0") and case IDs for
    # readability. They are correct for the current run; if the eval is re-run with different data,
    # re-read these notes (the eval re-run reopens the results gate anyway).
    m = summary.get("meta", {})
    cfgs = summary["configs"]
    d, dr, dj = summary["deltas"], summary.get("deltas_rule", {}), summary.get("deltas_judge", {})
    test = m.get("test", []) or []
    pc_all = _percase(runs) if runs else {}

    # held-out arm means (single·opt vs multi·opt) for the headline
    def test_arm_mean(cfg: str):
        vals = [pc_all[c][cfg]["composite"] for c in test if c in pc_all and pc_all[c].get(cfg)]
        vals = [v for v in vals if v is not None]
        return round(statistics.mean(vals), 4) if vals else None
    so_test, mo_test = test_arm_mean("single_agent_optimized"), test_arm_mean("multi_agent_optimized")

    L: list[str] = []
    L.append("# C4 — Reliability evaluation results\n")
    L.append(f"- **Model (pinned):** {m.get('model', '?')} · temperature {m.get('temperature', 0)}")
    L.append(f"- **Cases:** {m.get('n_cases', '?')} synthetic · **runs/case:** {m.get('runs_per_case', '?')} · "
             f"**held-out TEST split (n={len(test)}):** {', '.join(test) or '?'}")
    L.append(f"- **Primary metric:** gold-grounded LLM grader composite; **cross-check:** deterministic "
             f"rules; secondary **holistic judge** (it *dissents* on the prompt-opt contrasts — see §2).")
    L.append(f"- {m.get('no_significance_claim', 'descriptive profile; no significance claimed')}.")
    if m.get("failed_scores"):
        L.append(f"- ⚠️ {m['failed_scores']} run(s) lacked a primary score (excluded, counted as n_failed).")

    # ---- Headline: lead with the held-out result, honestly ----
    L.append("\n## Headline (held-out TEST)\n")
    L.append("- **Prompt optimization is the robust, generalizing win.** On the held-out split it lifts "
             f"the single agent by **{_sign(d.get('prompt_opt_for_single_TEST', {}).get('delta'))}** "
             f"(primary) / {_sign(dr.get('prompt_opt_for_single_TEST', {}).get('delta'))} (rule), by fixing "
             "concrete failures — it removes a fabricated TNM stage (E-CON-04) and fully de-identifies the "
             "held-out PII case (E-PII-02).")
    L.append(f"- **The single·optimized arm is the best held-out config ({_f(so_test)})**, ahead of "
             f"multi·optimized ({_f(mo_test)}). The 2×2 'best' arm (multi·optimized, §1) is best only "
             "*in-sample* (train-inclusive).")
    L.append("- **The multi-agent QC loop is targeted, not a uniform win.** Its contradiction-surfacing "
             "gain is **train-concentrated** (the self-correction *behind that gain* fired only on the two "
             "TRAIN contradiction cases; on held-out contradiction cases prompt-opt alone already maxed the "
             "score; the loop did also self-correct held-out E-PII-02, with the opposite effect — see below), "
             f"so on the held-out split it adds nothing (QC-loop @optimized TEST = "
             f"{_sign(d.get('qc_loop_at_optimized_TEST', {}).get('delta'))}).")
    L.append("- **Safety-relevant negative:** on one held-out case (E-PII-02) the QC self-correction loop "
             "**re-introduced the patient's name and MRN** that the single agent had correctly omitted "
             "(`no_pii_leak` 1.0 → 0.0; composite 1.0 → 0.667). Disclosed, not fixed away — see §6.")

    L.append("\n## 1. Configurations (2×2 factorial)\n")
    L.append("| Config | LLM composite | rule (x-check) | judge | self-corrected | run-to-run σ | n_failed |")
    L.append("|---|---|---|---|---|---|---|")
    for c in CONFIGS:
        s = cfgs.get(c, {})
        L.append(f"| {CFG_LABEL[c]} | **{_f(s.get('macro_composite'))}** | {_f(s.get('rule_macro_composite'))} | "
                 f"{_f(s.get('judge_mean'))} | {_f(s.get('self_corrected_rate'))} | "
                 f"{_f(s.get('mean_run_to_run_stdev'))} | {s.get('n_failed', 0)} |")
    L.append("\n_These are **all-15-case** means (train-inclusive). multi·optimized is highest here, but on "
             f"the **held-out** split single·optimized ({_f(so_test)}) edges multi·optimized ({_f(mo_test)}); "
             "the QC loop's all-case edge is carried by its two TRAIN contradiction cases (§3, §4)._")

    L.append("\n## 2. Before/after deltas (paired; all three metrics)\n")
    L.append("Δ = a − b on cases scored in **both** arms (n_paired). Direction = cases improved↑ / "
             "regressed↓ / tied= on the primary metric.\n")
    L.append("| Contrast | Δ LLM (primary) | Δ rule | Δ judge | n_paired | direction (primary) |")
    L.append("|---|---|---|---|---|---|")
    for label, key in DELTA_ROWS:
        v = d.get(key, {})
        L.append(f"| {label} | **{_sign(v.get('delta'))}** | {_sign(dr.get(key, {}).get('delta'))} | "
                 f"{_sign(dj.get(key, {}).get('delta'))} | {v.get('n_paired', 0)} | {_dirn(v)} |")
    L.append("\n_The holistic **judge dissents** on the prompt-opt TEST contrasts (Δ judge −0.037 while "
             "Δ LLM/rule are positive). This is a **real finding that vindicates the gold-grounded grader as "
             "primary**, not a wash: inspecting the drafts, on E-CON-04 the judge rates the baseline that "
             "**fabricates** stage `pT2b` (0.9) ABOVE the optimized draft that flags the missing stage (0.8) — "
             "i.e. it is fooled by a confident fabrication — and on E-GAP-02 it mildly penalizes the explicit "
             "`[DATA GAP]` marker's verbosity where both drafts are already fully reliable. The judge measures "
             "holistic *style/quality*; the primary measures *reliability*, which is the right axis here. The "
             "judge **does** corroborate the all-case / combined contrasts (positive Δ judge)._")

    pc = summary.get("per_category", {})
    if pc:
        L.append("\n## 3. Where it helps — per category (primary composite)\n")
        L.append("| Category | n | single·base | single·opt | multi·base | multi·opt | QC-loop Δ | combined Δ |")
        L.append("|---|---|---|---|---|---|---|---|")
        for cat, s in pc.items():
            mc = s.get("macro_composite", {})
            L.append(f"| {cat} | {s.get('n_cases', '?')} | {_f(mc.get('single_agent_baseline'))} | "
                     f"{_f(mc.get('single_agent_optimized'))} | {_f(mc.get('multi_agent_baseline'))} | "
                     f"{_f(mc.get('multi_agent_optimized'))} | {_sign(s.get('qc_loop_optimized', {}).get('delta'))} | "
                     f"{_sign(s.get('combined_worst_to_best', {}).get('delta'))} |")
        L.append("\n_This table is **all-case** (train + test). The contradiction `QC-loop Δ` (+0.188) is "
                 "**train-concentrated**: the contradiction self-correction fired on E-CON-01 and E-CON-03 "
                 "(TRAIN) only; the two held-out contradiction cases (E-CON-02, E-CON-04) were already maxed "
                 "by prompt-opt, so the QC loop adds nothing to them. The pii_leak `QC-loop Δ` (−0.167) is the "
                 "held-out PHI regression on E-PII-02 (§6) — where the loop *did* self-correct, re-inserting "
                 "the identifiers._")

    # ---- Held-out, per case (the vivid, fair view) ----
    if pc_all and test:
        L.append("\n## 4. Held-out TEST — per case (primary composite)\n")
        L.append("The 8 held-out cases, scored under each arm. Most are already perfect; the signal lives in "
                 "two cases — and so does the one regression.\n")
        L.append("| Case | category | single·base | single·opt | multi·base | multi·opt | what changed |")
        L.append("|---|---|---|---|---|---|---|")
        for cid in test:
            c = pc_all.get(cid, {})
            g = lambda k: _f(c.get(k, {}).get("composite"))  # noqa: E731
            L.append(f"| {cid} | {c.get('single_agent_baseline', {}).get('category', '?')} | "
                     f"{g('single_agent_baseline')} | {g('single_agent_optimized')} | "
                     f"{g('multi_agent_baseline')} | {g('multi_agent_optimized')} | {_case_note(c)} |")
        L.append("\n_E-CON-04: baseline invents stage `pT2b`; prompt-opt flags the gap instead (composite "
                 "0.583→1.0). E-PII-02: prompt-opt fully de-identifies (0.5→1.0), but the multi-agent QC loop's "
                 "self-correction re-inserts the patient name + MRN (1.0→0.667) — the held-out PHI regression._")

    L.append("\n## 5. Per-dimension reliability — the robust held-out win (single·baseline → single·optimized)\n")
    L.append("Prompt-optimization is the intervention that generalizes, so the honest worst→best axis is "
             "single·baseline → single·**optimized** (the top held-out arm), not the in-sample multi·optimized.\n")
    sb = cfgs.get("single_agent_baseline", {}).get("per_dimension_llm", {})
    so = cfgs.get("single_agent_optimized", {}).get("per_dimension_llm", {})
    mo = cfgs.get("multi_agent_optimized", {}).get("per_dimension_llm", {})
    L.append("| Dimension | single·baseline | single·optimized | Δ | (multi·optimized) |")
    L.append("|---|---|---|---|---|")
    for dim in DIMS:
        b, a, mv = sb.get(dim), so.get(dim), mo.get(dim)
        delta = (round(a - b, 3) if a is not None and b is not None else None)
        L.append(f"| {dim} | {_f(b)} | {_f(a)} | {_sign(delta)} | {_f(mv)} |")
    L.append("\n_The trailing `(multi·optimized)` column is **all-case**. The QC loop's per-dimension "
             "advantages over single·optimized — `contradiction_surfaced` (0.5→1.0) and `faithfulness` "
             "(0.933→1.0) — come **entirely from the two TRAIN contradiction cases** (E-CON-01/03, where "
             "self-correction fired); they do **not** hold on the held-out split (QC-loop @optimized TEST = "
             "−0.042, §2). Meanwhile the QC loop **regresses `no_pii_leak` (1.000 → 0.933)** by re-introducing "
             "PHI on E-PII-02. Prompt-opt's gains (`no_fabricated_stage`, `gap_flagged`, `no_pii_leak`) are the "
             "ones that generalize._")

    L.append("\n## 6. Measurement trust & limitations\n")
    L.append("**Grader validity.** The gold-grounded grader was independently checked (`eval/validate_grader.py`, "
             "evidence in `eval/evidence/grader_validation.txt`): **9/9 discrimination** (correct vs single-"
             "dimension-corrupted drafts) and **3/3 style-neutrality** (equal-reliability drafts score equally "
             "whether they use a `[DATA GAP]`/`discordant` marker or natural prose) — so the gains reflect "
             "reliability, not marker-gaming. The E-CON-04 judge result above is direct evidence for why a "
             "gold-grounded primary (not a holistic judge) is the right headline metric.")
    L.append("\n**Judge-429 integrity.** The agent runs and primary/cross-check scores completed with **no gaps** "
             "(n_failed = 0). Some auxiliary triangulation-judge calls hit a transient Vertex 429; an auditor "
             "(`eval/verify_judge_integrity.py`, evidence in `eval/evidence/judge_integrity.txt`) confirms those "
             "gaps are **score-preserving** — at temperature 0 the drafts are byte-identical across a case's runs "
             "and the surviving judge values agree exactly, so judge means/deltas equal a zero-gap run.")
    L.append("\n**Honest limitations.**")
    L.append("- **The QC self-correction loop can re-introduce PHI.** On held-out E-PII-02 it re-inserted the "
             "patient name + MRN the single agent had removed. A deterministic PII-scrub post-step (out of C4 "
             "scope) is the indicated mitigation; until then the QC loop is not safe to ship for de-identification.")
    L.append("- **The QC loop's contradiction benefit is train-concentrated and did not generalize** "
             "(QC-loop @optimized TEST = " + _sign(d.get("qc_loop_at_optimized_TEST", {}).get("delta")) + ").")
    L.append("- **n=15 (TEST n=8): a descriptive reliability profile; no statistical significance is claimed.** "
             "The optimizer selects augmentations on TRAIN by the deterministic composite; *_TEST deltas are the "
             "held-out generalization, *_all deltas (train-inclusive) are supplementary.")
    notes = summary.get("delta_notes", {})
    if notes:
        L.append(f"\n> _Method notes._ {notes.get('held_out', '')} {notes.get('pairing', '')}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="eval/outputs/<run_dir> (or a path to a summary.json)")
    ap.add_argument("--out", default="", help="write Markdown here (default: stdout)")
    args = ap.parse_args()
    p = Path(args.run_dir)
    run_dir = p.parent if p.name == "summary.json" else p
    summary = json.loads((run_dir / "summary.json").read_text())
    runs_path = run_dir / "runs.jsonl"
    runs = [json.loads(l) for l in runs_path.read_text().splitlines() if l.strip()] if runs_path.exists() else None
    md = render(summary, runs)
    if args.out:
        Path(args.out).write_text(md)
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
