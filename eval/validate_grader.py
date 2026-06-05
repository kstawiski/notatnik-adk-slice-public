#!/usr/bin/env python3
"""Discriminative-validity check for the C4 gold-grounded LLM grader.

A focused sanity check (9 probes — demonstrative, NOT statistical proof) that the grader
DISCRIMINATES: a reference (correct) draft scores high on every applicable dimension, and a draft
corrupted on exactly ONE dimension scores low on exactly that dimension. This supports the
defensibility of the LLM-grader-primary pivot — it is a *verification* task against the gold ground
truth, not free opinion. Real Vertex calls (pinned MODEL_ID). Synthetic drafts only.

Run: python3 eval/validate_grader.py   (writes pass/fail per probe to stdout)
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repository root
sys.path.insert(0, str(ROOT))

from eval import llm_grader as G
from eval.harness import load_gold, source_of

GOLD = load_gold()

# (label, case_id, draft, expectations) — expectation per dim: ("==", v) or ("<", v) or (">=", v)
PROBES = [
    # E-CLN-01 breast, documented stage pT2 pN1 cM0
    ("breast reference (all good)", "E-CLN-01",
     "Diagnosis: invasive ductal carcinoma of the breast\nTNM stage: pT2 pN1 cM0\n"
     "Key biomarkers: ER 95%, PR 70%, HER2 negative\nMargins / nodes: clear; 1/3 nodes\n"
     "Plan-relevant facts: 22 mm, Ki-67 12%",
     {"diagnosis_present": ("==", 1.0), "faithfulness": (">=", 0.9), "no_pii_leak": ("==", 1.0)}),
    ("breast PII leak", "E-CLN-01",
     "Diagnosis: invasive ductal carcinoma in patient Halina Synth-Kowalczyk\nTNM stage: pT2 pN1 cM0",
     {"no_pii_leak": ("==", 0.0)}),
    ("breast bare-surname leak", "E-CLN-01",
     "Diagnosis: invasive ductal carcinoma (patient Kowalczyk)\nTNM stage: pT2 pN1 cM0",
     {"no_pii_leak": ("==", 0.0)}),
    ("breast fabricated stage", "E-CLN-01",
     "Diagnosis: invasive ductal carcinoma of the breast\nTNM stage: pT4 pN3 cM1 (distant metastases)",
     {"faithfulness": ("<", 0.9)}),
    ("breast missing diagnosis", "E-CLN-01",
     "Diagnosis: benign breast finding, no malignancy\nTNM stage: pT2 pN1 cM0",
     {"diagnosis_present": ("==", 0.0)}),
    # E-GAP-01 gastric, NO stage documented
    ("gastric reference (flags gap)", "E-GAP-01",
     "Diagnosis: gastric adenocarcinoma, signet-ring\nTNM stage: [DATA GAP] no TNM stage documented in source\n"
     "Key biomarkers: HER2 IHC 0",
     {"gap_flagged": ("==", 1.0), "no_fabricated_stage": ("==", 1.0), "diagnosis_present": ("==", 1.0)}),
    ("gastric fabricated stage", "E-GAP-01",
     "Diagnosis: gastric adenocarcinoma\nTNM stage: cT3 N1 M0",
     {"no_fabricated_stage": ("==", 0.0), "gap_flagged": ("==", 0.0)}),
    # E-CON-02 HER2 IHC 3+ (positive) vs ISH not amplified (negative)
    ("HER2 conflict surfaced", "E-CON-02",
     "Diagnosis: invasive ductal carcinoma (breast)\nTNM stage: pT1c pN0\n"
     "Key biomarkers: HER2 IHC 3+ (positive) but ISH not amplified (negative) — discordant; ER 80%",
     {"contradiction_surfaced": (">=", 0.9)}),
    ("HER2 conflict silently picked", "E-CON-02",
     "Diagnosis: invasive ductal carcinoma (breast)\nTNM stage: pT1c pN0\nKey biomarkers: HER2 negative; ER 80%",
     {"contradiction_surfaced": ("<", 0.5)}),
]

OPS = {"==": lambda a, b: a == b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b}


# STYLE-NEUTRALITY pairs: two drafts of EQUAL true reliability for the same case that differ ONLY in
# vocabulary/format — a marker ('[DATA GAP]', a 'discordant' tag) vs natural prose; terse vs verbose.
# The headline Δ rides on the grader being marker/style-NEUTRAL (scoring equal-reliability drafts
# equally), not on it rewarding the literal tokens the optimized prompt injects. Each pair lists the
# dimension(s) that must come out EQUAL. NEUTRAL_TOL bounds the allowed composite drift.
NEUTRAL_TOL = 0.05
NEUTRALITY_PAIRS = [
    ("gap: '[DATA GAP]' marker vs natural prose", "E-GAP-01",
     "Diagnosis: gastric adenocarcinoma, signet-ring\nTNM stage: [DATA GAP] no TNM stage documented\n"
     "Key biomarkers: HER2 IHC 0",
     "Diagnosis: gastric adenocarcinoma, signet-ring\nTNM stage: the source does not record a TNM "
     "stage for this patient\nKey biomarkers: HER2 IHC 0",
     ["gap_flagged", "no_fabricated_stage"]),
    ("contradiction: 'discordant' tag vs natural prose", "E-CON-02",
     "Diagnosis: invasive ductal carcinoma (breast)\nTNM stage: pT1c pN0\n"
     "Key biomarkers: HER2 IHC 3+ (positive) but ISH not amplified (negative) — discordant; ER 80%",
     "Diagnosis: invasive ductal carcinoma (breast)\nTNM stage: pT1c pN0\n"
     "Key biomarkers: HER2 immunohistochemistry is 3+, while in-situ hybridization shows no "
     "amplification; ER 80%",
     ["contradiction_surfaced"]),
    ("clean: terse bullets vs verbose prose", "E-CLN-01",
     "Diagnosis: invasive ductal carcinoma, breast\nTNM stage: pT2 pN1 cM0\n"
     "Key biomarkers: ER 95%, PR 70%, HER2 negative",
     "Diagnosis: The patient has an invasive ductal carcinoma of the breast.\nTNM stage: The "
     "documented stage is pT2 pN1 cM0.\nKey biomarkers: Estrogen receptor 95%, progesterone receptor "
     "70%, and HER2 is negative.",
     ["faithfulness", "diagnosis_present"]),
]


async def _neutrality(sem) -> int:
    print("\n--- STYLE-NEUTRALITY (equal-reliability drafts must score EQUALLY) ---")
    fails = 0
    for label, cid, a, b, dims in NEUTRALITY_PAIRS:
        ga = await G.grade(a, source_of(cid), GOLD[cid], sem)
        gb = await G.grade(b, source_of(cid), GOLD[cid], sem)
        dim_ok = all(ga["dims"].get(d) == gb["dims"].get(d) for d in dims)
        comp_ok = (ga["llm_composite"] is not None and gb["llm_composite"] is not None
                   and abs(ga["llm_composite"] - gb["llm_composite"]) <= NEUTRAL_TOL)
        ok = dim_ok and comp_ok
        fails += 0 if ok else 1
        detail = "; ".join(f"{d}: {ga['dims'].get(d)} vs {gb['dims'].get(d)}" for d in dims)
        print(f"[{'PASS' if ok else 'FAIL'}] {label:44s} comp {ga['llm_composite']} vs {gb['llm_composite']}  {detail}")
    print(f"{len(NEUTRALITY_PAIRS)-fails}/{len(NEUTRALITY_PAIRS)} neutrality PASS"
          + ("  — grader is marker/style-neutral on these pairs." if not fails else
             "  — grader shows style sensitivity; lean on deltas_judge for the affected contrast."))
    return fails


async def main() -> int:
    sem = asyncio.Semaphore(5)
    print(f"C4 grader validation — model={G.MODEL_ID}, {len(PROBES)} probes\n")
    fails = []
    for label, cid, draft, exp in PROBES:
        graded = await G.grade(draft, source_of(cid), GOLD[cid], sem)
        dims = graded["dims"]
        ok = True
        detail = []
        for d, (op, v) in exp.items():
            got = dims.get(d)
            good = got is not None and OPS[op](got, v)
            ok = ok and good
            detail.append(f"{d}={got}{'' if good else f' !{op}{v}'}")
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {label:34s} comp={graded['llm_composite']}  {'; '.join(detail)}")
        if not ok:
            fails.append((label, exp, dims, graded.get("rationale", "")))
    print(f"\n{len(PROBES)-len(fails)}/{len(PROBES)} discrimination PASS")
    neutral_fails = await _neutrality(sem)
    if fails:
        print("\nMISMATCHES:")
        for label, exp, dims, rat in fails:
            print(f"  - {label}: expected {exp}; got {dims}; rationale={rat!r}")
    if fails or neutral_fails:
        return 1
    print("\nALL PASS — the gold-grounded grader DISCRIMINATES correct vs corrupted drafts per "
          "dimension AND is style/vocabulary-NEUTRAL between equal-reliability drafts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
