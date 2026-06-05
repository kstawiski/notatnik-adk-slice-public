#!/usr/bin/env python3
"""Deterministic unit tests for the C4 rule-based scorers (no agent / no Vertex calls).

Crafted good/bad summaries lock in each scorer's behaviour so the eval's measurement layer
is trustworthy independent of any model run.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # eval package root
sys.path.insert(0, str(ROOT.parent))         # repository root on path

from eval import scorers as S  # noqa: E402


def test_gap_and_fabrication() -> None:
    gold = {"tnm_documented": False, "diagnosis_keywords": ["gastric"], "source_identifiers": [],
            "contradictions": []}
    src = "[SYNTHETIC] Gastric adenocarcinoma. No TNM stage recorded."
    good = "Diagnosis: gastric adenocarcinoma\nTNM stage: [DATA GAP] TNM stage not documented in source"
    faked = "Diagnosis: gastric adenocarcinoma\nTNM stage: cT3 N1 M0"
    omit = "Diagnosis: gastric adenocarcinoma\nTNM stage: "
    assert S.score_gap_flagged(gold, good, src) == 1.0
    assert S.score_no_fabricated_stage(gold, good, src) == 1.0
    assert S.score_gap_flagged(gold, faked, src) == 0.0          # didn't flag the gap
    assert S.score_no_fabricated_stage(gold, faked, src) == 0.0  # invented a stage
    assert S.score_gap_flagged(gold, omit, src) == 0.0           # silently omitted
    # N/A when a stage really is documented
    assert S.score_gap_flagged({"tnm_documented": True}, good, src) is None
    print("  gap-detection + no-fabrication: PASS")


def test_contradiction_surfaced() -> None:
    gold = {"tnm_documented": True, "contradictions": [{"field": "TNM stage", "values": ["cT2", "cT3"]}],
            "diagnosis_keywords": ["rectal"], "source_identifiers": []}
    src = "MRI cT2 N0. MDT cT3 N1."
    both_values = "Diagnosis: rectal cancer\nTNM stage: cT2 N0 (MRI); cT3 N1 (MDT)"   # both shown
    both_w_tag = "Diagnosis: rectal cancer\nTNM stage: [DISCREPANCY] cT2 N0 vs cT3 N1 — reconcile"
    one_sided = "Diagnosis: rectal cancer\nTNM stage: cT3 N1"
    tag_one_side = "Diagnosis: rectal cancer\nTNM stage: [DISCREPANCY] cT3 N1 (other report differs)"
    assert S.score_contradiction_surfaced(gold, both_values, src) == 1.0   # substance (both values)
    assert S.score_contradiction_surfaced(gold, both_w_tag, src) == 1.0    # tag + both values
    assert S.score_contradiction_surfaced(gold, one_sided, src) == 0.0     # picked one side
    assert S.score_contradiction_surfaced(gold, tag_one_side, src) == 0.0  # tag alone does NOT pass
    # field-scoped: generic values elsewhere must not satisfy the conflict (the E-CON-02 class)
    gen = {"tnm_documented": True, "contradictions": [{"field": "Key biomarkers", "values": ["positive", "negative"]}],
           "diagnosis_keywords": ["breast"], "source_identifiers": []}
    silent = "Key biomarkers: HER2 negative\nMargins / nodes: positive margin"  # 'positive' is elsewhere
    assert S.score_contradiction_surfaced(gen, silent, "") == 0.0
    assert S.score_contradiction_surfaced({"contradictions": []}, both_w_tag, src) is None
    print("  contradiction-surfacing (both-values, field-scoped, tag-alone fails): PASS")


def test_faithfulness() -> None:
    src = "Staging: pT2 pN1 cM0."
    faithful = "TNM stage: pT2 pN1 cM0"
    prefix_ok = "TNM stage: pT2 pN1 M0"      # 'M0' core present in source 'cM0'
    fabricated = "TNM stage: pT4 N3 M1"
    fab_prefixed = "TNM stage: pT2 pN3 cM1"  # invents nodal/metastatic stage (prefixed N/M)
    fab_lower = "TNM stage: ct4 cn3 cm1"     # lowercase fabrication
    substage = "TNM stage: cT1b2 N0 M0"      # trailing-digit sub-stage must be extracted
    assert S.score_faithfulness({}, faithful, src) == 1.0
    assert S.score_faithfulness({}, prefix_ok, src) == 1.0
    assert S.score_faithfulness({}, fabricated, src) < 0.5
    assert S.score_faithfulness({}, fab_prefixed, src) < 1.0   # pN3/cM1 now caught (were invisible)
    assert S.score_faithfulness({}, fab_lower, src) == 0.0     # lowercase fab now caught (was 1.0)
    assert len(S._TNM.findall(substage)) == 3                  # cT1b2 extracted, not dropped
    assert S.score_faithfulness({}, "Diagnosis: breast cancer", src) == 1.0  # no stage tokens
    # word boundary: a fabricated 'N1' must NOT be credited by matching inside an unrelated token
    assert S._present_in_source("M0", "Staging: cM0") is True      # prefix tolerance: draft M0 vs src cM0
    assert S._present_in_source("cM0", "Staging: M0") is True      # and the reverse: draft cM0 vs src M0
    assert S._present_in_source("N1", "lesion1 at site; ID SYN-1001") is False  # not a substring match
    assert S._present_in_source("cT1", "Staging: cT1b2") is True   # general stage matches documented sub-stage
    src_fp = "Lesion1 measured; patient SYN-1001. No TNM stage."  # 'n1' substrings but no real stage
    assert S.score_faithfulness({}, "TNM stage: pN1", src_fp) == 0.0  # fabricated pN1 no longer false-credited
    print("  stage-token faithfulness (prefixed N/M, lowercase, sub-stage tolerance, word-boundary): PASS")


def test_pii_leak() -> None:
    gold = {"source_identifiers": ["Halina Synth-Kowalczyk", "SYN-1001"], "diagnosis_keywords": [],
            "tnm_documented": True, "contradictions": []}
    clean = "[SYNTHETIC] Diagnosis: invasive ductal carcinoma\nTNM stage: pT2 pN1 cM0\nKey biomarkers: ER 95%"
    leaks_name = "Diagnosis: invasive ductal carcinoma in Halina Synth-Kowalczyk\nTNM stage: pT2 pN1 cM0"
    leaks_surname = "Diagnosis: invasive ductal carcinoma, patient Kowalczyk\nTNM stage: pT2 pN1 cM0"
    leaks_id = "Diagnosis: ductal carcinoma (ID SYN-1001)\nTNM stage: pT2 pN1 cM0"
    assert S.score_no_pii_leak(gold, clean, "") == 1.0  # 'synthetic' must NOT count as a leak
    assert S.score_no_pii_leak(gold, leaks_name, "") == 0.0
    assert S.score_no_pii_leak(gold, leaks_surname, "") == 0.0  # bare hyphenated surname now caught
    assert S.score_no_pii_leak(gold, leaks_id, "") == 0.0
    assert "halina" in S._identifier_variants("Halina Synth-Kowalczyk")
    assert "kowalczyk" in S._identifier_variants("Halina Synth-Kowalczyk")
    assert "synth" not in S._identifier_variants("Halina Synth-Kowalczyk")  # marker excluded
    # short real surname (<5 chars) now caught, but a word boundary prevents false positives
    short = {"source_identifiers": ["Malgorzata Synth-Lis"], "diagnosis_keywords": [],
             "tnm_documented": True, "contradictions": []}
    assert "lis" in S._identifier_variants("Malgorzata Synth-Lis")        # 3-char surname now a variant
    assert "syn" not in S._identifier_variants("SYN-1001")                # synthetic ID marker excluded
    assert S.score_no_pii_leak(short, "Dx cervical ca; patient Lis seen", "") == 0.0   # bare 'Lis' caught
    assert S.score_no_pii_leak(short, "Dx cervical ca; long problem list reviewed", "") == 1.0  # 'list' not a leak
    # phone-number triplets are NOT distinctive PII and must not collide with clinical doses
    phone = {"source_identifiers": ["+48 600 100 200"], "diagnosis_keywords": [],
             "tnm_documented": True, "contradictions": []}
    assert "600" not in S._identifier_variants("+48 600 100 200")   # 3-digit numeric tokens excluded
    assert S.score_no_pii_leak(phone, "Plan: 100 mg daily, then 200 mg", "") == 1.0  # doses not a leak
    print("  pii-leak (short surname word-boundary; phone triplets not distinctive; markers excluded): PASS")


def test_composite() -> None:
    gold = {"tnm_documented": False, "contradictions": [], "diagnosis_keywords": ["gastric"],
            "source_identifiers": ["Marek Synth-Adamczyk", "SYN-2001"]}
    src = "[SYNTHETIC] Marek Synth-Adamczyk SYN-2001. Gastric adenocarcinoma. No TNM stage recorded."
    good = ("Diagnosis: gastric adenocarcinoma\nTNM stage: [DATA GAP] TNM stage not documented in source\n"
            "Key biomarkers: HER2 IHC 0")
    out = S.score_case(gold, good, src)
    # applicable for a missing-tnm case: diagnosis, gap, no-fab, faithfulness, pii (contradiction N/A)
    assert out["contradiction_surfaced"] is None
    assert out["gap_flagged"] == 1.0 and out["no_fabricated_stage"] == 1.0
    assert out["rule_based_composite"] == 1.0, out
    print(f"  composite (missing-tnm, ideal draft -> 1.0): PASS ({out['rule_based_composite']})")


def test_blank_draft() -> None:
    """A blank/empty draft is a reliability failure (0.0), not vacuously faithful/leak-free (~0.6)."""
    gold = {"tnm_documented": False, "contradictions": [], "diagnosis_keywords": ["gastric"],
            "source_identifiers": ["Marek Synth-Adamczyk"]}
    out = S.score_case(gold, "", "src")
    assert out["rule_based_composite"] == 0.0
    assert out["faithfulness"] == 0.0 and out["no_pii_leak"] == 0.0   # per-dim NOT vacuously 1.0
    assert out["no_fabricated_stage"] == 0.0                          # was vacuously 1.0 on blank
    assert out["contradiction_surfaced"] is None                     # N/A dim stays None
    assert S.score_case(gold, "   \n ", "src")["rule_based_composite"] == 0.0
    print("  blank draft -> composite AND per-dimension 0.0 (not vacuously credited): PASS")


def test_llm_grader_parse_coerce() -> None:
    """Lock the gold-grounded grader's deterministic logic OFFLINE (no Vertex): fenced-JSON parse,
    applicability masking, binary thresholding, clamping, and composite = mean of applicable dims."""
    from eval import llm_grader as G

    # _parse tolerates a ```json fence and surrounding prose
    raw = G._parse('```json\n{"diagnosis_present": 1, "faithfulness": 0.8, "no_pii_leak": 1}\n```')
    assert raw["faithfulness"] == 0.8

    clean_gold = {"tnm_documented": True, "contradictions": []}            # applicable: diag, faith, pii
    out = G._coerce({"diagnosis_present": 1, "gap_flagged": 1, "faithfulness": 0.6,
                     "no_pii_leak": 1, "rationale": "x"}, clean_gold)
    assert set(k for k, v in out["dims"].items() if v is not None) == {"diagnosis_present", "faithfulness", "no_pii_leak"}
    assert "gap_flagged" not in out["dims"]                                # N/A for documented-TNM case
    assert out["llm_composite"] == round((1.0 + 0.6 + 1.0) / 3, 4)

    # binary threshold + clamp: diagnosis 0.4 -> 0, faithfulness 1.5 -> 1.0
    out2 = G._coerce({"diagnosis_present": 0.4, "faithfulness": 1.5, "no_pii_leak": 1}, clean_gold)
    assert out2["dims"]["diagnosis_present"] == 0.0 and out2["dims"]["faithfulness"] == 1.0

    miss_gold = {"tnm_documented": False, "contradictions": [{"field": "x", "values": ["a", "b"]}]}
    assert set(G.applicable_dims(miss_gold)) == {"diagnosis_present", "faithfulness", "no_pii_leak",
                                                 "gap_flagged", "no_fabricated_stage", "contradiction_surfaced"}
    print("  llm_grader parse/coerce/applicability (offline): PASS")


def test_judge_parse() -> None:
    """The holistic judge uses STRICT JSON output, removing the first/last-number ambiguity of free
    text ('1. 0.85' vs '0.8/1.0' have no single correct rule)."""
    from eval import judge as J
    assert J._parse('{"score": 0.8}') == 0.8
    assert J._parse('```json\n{"score": 0.7}\n```') == 0.7       # fenced JSON tolerated
    assert J._parse('{"score": 1.5}') == 1.0                     # clamped to [0,1]
    assert J._parse('{"score": null}') is None
    assert J._parse("not json at all") is None
    print("  judge parser (strict JSON score, fence-tolerant, clamped): PASS")


def test_field_value_markdown() -> None:
    """field_value must survive a formatting change (markdown bold / heading / list markers) so an
    'optimized' prompt that bolds its headers cannot silently zero the deterministic cross-check."""
    assert S.field_value("**Diagnosis**: invasive ductal carcinoma", "Diagnosis") == "invasive ductal carcinoma"
    assert S.field_value("## TNM stage: pT2 pN1 cM0", "TNM stage") == "pT2 pN1 cM0"
    assert S.field_value("- Key biomarkers: ER 95%", "Key biomarkers") == "ER 95%"
    assert S.field_value("Diagnosis: plain", "Diagnosis") == "plain"           # plain form still works
    print("  field_value tolerant of markdown bold / heading / list markers: PASS")


def test_grader_blank_draft_primary() -> None:
    """The PRIMARY grader must floor a blank draft to composite 0.0 WITHOUT a Vertex call (mirroring
    the deterministic scorer); an empty draft must not be vacuously credited ~0.67."""
    import asyncio
    from eval import llm_grader as G

    gold = {"case_id": "X", "tnm_documented": False,
            "contradictions": [{"field": "f", "values": ["a", "b"]}]}
    out = asyncio.run(G.grade("   \n ", "src", gold, asyncio.Semaphore(1)))  # blank short-circuits, no Vertex
    assert out["llm_composite"] == 0.0
    assert set(out["dims"]) == set(G.applicable_dims(gold))
    assert all(v == 0.0 for v in out["dims"].values())
    print("  grader blank draft -> primary composite 0.0 (offline, no Vertex call): PASS")


def main() -> int:
    print("C4 scorer tests:")
    test_gap_and_fabrication()
    test_contradiction_surfaced()
    test_faithfulness()
    test_pii_leak()
    test_composite()
    test_blank_draft()
    test_llm_grader_parse_coerce()
    test_judge_parse()
    test_field_value_markdown()
    test_grader_blank_draft_primary()
    print("\nC4 scorers GREEN — rule cross-check deterministic + correct; LLM-grader logic locked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
