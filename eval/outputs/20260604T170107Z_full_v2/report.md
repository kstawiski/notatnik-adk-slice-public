# C4 — Reliability evaluation results

- **Model (pinned):** gemini-3.1-flash-lite (pinned) · temperature 0
- **Cases:** 15 synthetic · **runs/case:** 3 · **held-out TEST split (n=8):** E-CLN-02, E-CLN-04, E-CON-02, E-CON-04, E-FTH-01, E-GAP-02, E-GAP-04, E-PII-02
- **Primary metric:** gold-grounded LLM grader composite; **cross-check:** deterministic rules; secondary **holistic judge** (it *dissents* on the prompt-opt contrasts — see §2).
- n=15 cases; descriptive reliability profile only.

## Headline (held-out TEST)

- **Prompt optimization is the robust, generalizing win.** On the held-out split it lifts the single agent by **+0.115** (primary) / +0.098 (rule), by fixing concrete failures — it removes a fabricated TNM stage (E-CON-04) and fully de-identifies the held-out PII case (E-PII-02).
- **The single·optimized arm is the best held-out config (1.000)**, ahead of multi·optimized (0.958). The 2×2 'best' arm (multi·optimized, §1) is best only *in-sample* (train-inclusive).
- **The multi-agent QC loop is targeted, not a uniform win.** Its contradiction-surfacing gain is **train-concentrated** (the self-correction *behind that gain* fired only on the two TRAIN contradiction cases; on held-out contradiction cases prompt-opt alone already maxed the score; the loop did also self-correct held-out E-PII-02, with the opposite effect — see below), so on the held-out split it adds nothing (QC-loop @optimized TEST = -0.042).
- **Safety-relevant negative:** on one held-out case (E-PII-02) the QC self-correction loop **re-introduced the patient's name and MRN** that the single agent had correctly omitted (`no_pii_leak` 1.0 → 0.0; composite 1.0 → 0.667). Disclosed, not fixed away — see §6.

## 1. Configurations (2×2 factorial)

| Config | LLM composite | rule (x-check) | judge | self-corrected | run-to-run σ | n_failed |
|---|---|---|---|---|---|---|
| single · baseline | **0.867** | 0.876 | 0.873 | 0.000 | 0.000 | 0 |
| single · optimized | **0.950** | 0.950 | 0.880 | 0.000 | 0.000 | 0 |
| multi · baseline | **0.889** | 0.898 | 0.873 | 0.000 | 0.000 | 0 |
| multi · optimized | **0.978** | 0.961 | 0.907 | 0.200 | 0.000 | 0 |

_These are **all-15-case** means (train-inclusive). multi·optimized is highest here, but on the **held-out** split single·optimized (1.000) edges multi·optimized (0.958); the QC loop's all-case edge is carried by its two TRAIN contradiction cases (§3, §4)._

## 2. Before/after deltas (paired; all three metrics)

Δ = a − b on cases scored in **both** arms (n_paired). Direction = cases improved↑ / regressed↓ / tied= on the primary metric.

| Contrast | Δ LLM (primary) | Δ rule | Δ judge | n_paired | direction (primary) |
|---|---|---|---|---|---|
| QC-loop @ baseline (all) | **+0.022** | +0.022 | 0.000 | 15 | 1↑ / 0↓ / 14= |
| QC-loop @ optimized (all) | **+0.028** | +0.011 | +0.027 | 15 | 2↑ / 1↓ / 12= |
| QC-loop @ optimized (TEST) | **-0.042** | -0.042 | 0.000 | 8 | 0↑ / 1↓ / 7= |
| Prompt-opt, multi (TEST) | **+0.073** | +0.056 | -0.037 | 8 | 2↑ / 0↓ / 6= |
| Prompt-opt, single (TEST) | **+0.115** | +0.098 | -0.037 | 8 | 2↑ / 0↓ / 6= |
| Combined worst→best (TEST) | **+0.073** | +0.056 | -0.037 | 8 | 2↑ / 0↓ / 6= |

_The holistic **judge dissents** on the prompt-opt TEST contrasts (Δ judge −0.037 while Δ LLM/rule are positive). This is a **real finding that vindicates the gold-grounded grader as primary**, not a wash: inspecting the drafts, on E-CON-04 the judge rates the baseline that **fabricates** stage `pT2b` (0.9) ABOVE the optimized draft that flags the missing stage (0.8) — i.e. it is fooled by a confident fabrication — and on E-GAP-02 it mildly penalizes the explicit `[DATA GAP]` marker's verbosity where both drafts are already fully reliable. The judge measures holistic *style/quality*; the primary measures *reliability*, which is the right axis here. The judge **does** corroborate the all-case / combined contrasts (positive Δ judge)._

## 3. Where it helps — per category (primary composite)

| Category | n | single·base | single·opt | multi·base | multi·opt | QC-loop Δ | combined Δ |
|---|---|---|---|---|---|---|---|
| clean | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| contradiction | 4 | 0.708 | 0.812 | 0.708 | 1.000 | +0.188 | +0.292 |
| faithfulness | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| missing_tnm | 4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| pii_leak | 2 | 0.583 | 1.000 | 0.750 | 0.833 | -0.167 | +0.250 |

_This table is **all-case** (train + test). The contradiction `QC-loop Δ` (+0.188) is **train-concentrated**: the contradiction self-correction fired on E-CON-01 and E-CON-03 (TRAIN) only; the two held-out contradiction cases (E-CON-02, E-CON-04) were already maxed by prompt-opt, so the QC loop adds nothing to them. The pii_leak `QC-loop Δ` (−0.167) is the held-out PHI regression on E-PII-02 (§6) — where the loop *did* self-correct, re-inserting the identifiers._

## 4. Held-out TEST — per case (primary composite)

The 8 held-out cases, scored under each arm. Most are already perfect; the signal lives in two cases — and so does the one regression.

| Case | category | single·base | single·opt | multi·base | multi·opt | what changed |
|---|---|---|---|---|---|---|
| E-CLN-02 | clean | 1.000 | 1.000 | 1.000 | 1.000 | all arms perfect |
| E-CLN-04 | clean | 1.000 | 1.000 | 1.000 | 1.000 | all arms perfect |
| E-CON-02 | contradiction | 1.000 | 1.000 | 1.000 | 1.000 | all arms perfect |
| E-CON-04 | contradiction | 0.583 | 1.000 | 0.583 | 1.000 | prompt-opt fixes (+0.417); QC loop neutral |
| E-FTH-01 | faithfulness | 1.000 | 1.000 | 1.000 | 1.000 | all arms perfect |
| E-GAP-02 | missing_tnm | 1.000 | 1.000 | 1.000 | 1.000 | all arms perfect |
| E-GAP-04 | missing_tnm | 1.000 | 1.000 | 1.000 | 1.000 | all arms perfect |
| E-PII-02 | pii_leak | 0.500 | 1.000 | 0.500 | 0.667 | prompt-opt fixes (+0.500); **QC loop regresses (-0.333)** |

_E-CON-04: baseline invents stage `pT2b`; prompt-opt flags the gap instead (composite 0.583→1.0). E-PII-02: prompt-opt fully de-identifies (0.5→1.0), but the multi-agent QC loop's self-correction re-inserts the patient name + MRN (1.0→0.667) — the held-out PHI regression._

## 5. Per-dimension reliability — the robust held-out win (single·baseline → single·optimized)

Prompt-optimization is the intervention that generalizes, so the honest worst→best axis is single·baseline → single·**optimized** (the top held-out arm), not the in-sample multi·optimized.

| Dimension | single·baseline | single·optimized | Δ | (multi·optimized) |
|---|---|---|---|---|
| diagnosis_present | 1.000 | 1.000 | 0.000 | 1.000 |
| gap_flagged | 0.833 | 1.000 | +0.167 | 1.000 |
| no_fabricated_stage | 0.833 | 1.000 | +0.167 | 1.000 |
| contradiction_surfaced | 0.500 | 0.500 | 0.000 | 1.000 |
| faithfulness | 0.867 | 0.933 | +0.067 | 1.000 |
| no_pii_leak | 0.867 | 1.000 | +0.133 | 0.933 |

_The trailing `(multi·optimized)` column is **all-case**. The QC loop's per-dimension advantages over single·optimized — `contradiction_surfaced` (0.5→1.0) and `faithfulness` (0.933→1.0) — come **entirely from the two TRAIN contradiction cases** (E-CON-01/03, where self-correction fired); they do **not** hold on the held-out split (QC-loop @optimized TEST = −0.042, §2). Meanwhile the QC loop **regresses `no_pii_leak` (1.000 → 0.933)** by re-introducing PHI on E-PII-02. Prompt-opt's gains (`no_fabricated_stage`, `gap_flagged`, `no_pii_leak`) are the ones that generalize._

## 6. Measurement trust & limitations

**Grader validity.** The gold-grounded grader was independently checked (`eval/validate_grader.py`, evidence in `eval/evidence/grader_validation.txt`): **9/9 discrimination** (correct vs single-dimension-corrupted drafts) and **3/3 style-neutrality** (equal-reliability drafts score equally whether they use a `[DATA GAP]`/`discordant` marker or natural prose) — so the gains reflect reliability, not marker-gaming. The E-CON-04 judge result above is direct evidence for why a gold-grounded primary (not a holistic judge) is the right headline metric.

**Judge-429 integrity.** The agent runs and primary/cross-check scores completed with **no gaps** (n_failed = 0). Some auxiliary triangulation-judge calls hit a transient Vertex 429; an auditor (`eval/verify_judge_integrity.py`, evidence in `eval/evidence/judge_integrity.txt`) confirms those gaps are **score-preserving** — at temperature 0 the drafts are byte-identical across a case's runs and the surviving judge values agree exactly, so judge means/deltas equal a zero-gap run.

**Honest limitations.**
- **The QC self-correction loop can re-introduce PHI.** On held-out E-PII-02 it re-inserted the patient name + MRN the single agent had removed. A deterministic PII-scrub post-step (out of C4 scope) is the indicated mitigation; until then the QC loop is not safe to ship for de-identification.
- **The QC loop's contradiction benefit is train-concentrated and did not generalize** (QC-loop @optimized TEST = -0.042).
- **n=15 (TEST n=8): a descriptive reliability profile; no statistical significance is claimed.** The optimizer selects augmentations on TRAIN by the deterministic composite; *_TEST deltas are the held-out generalization, *_all deltas (train-inclusive) are supplementary.

> _Method notes._ augmentations are selected on TRAIN by the deterministic composite; *_TEST deltas are the held-out generalization. *_all deltas include TRAIN (in-sample) — supplementary. each delta uses cases with a valid score (for that metric) in BOTH configs (n_paired). Pairing removes denominator-mismatch bias; it does NOT remove informative-missingness bias, so if failures concentrate in a weaker config a contrast is conservatively biased toward null — n_failed is reported per config (and per category) to make this visible.
