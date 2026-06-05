# Reliability Delta Summary

Source artifact: `eval/outputs/20260604T170107Z_full_v2/report.md`.

Evaluation setup:

- 15 synthetic oncology cases.
- 3 runs per case.
- Temperature 0.
- Held-out TEST split: 8 cases.
- Primary metric: gold-grounded LLM grader composite.
- Cross-check: deterministic rule score.
- Descriptive reliability profile only; no significance claim at n=15.

## Reliability Summary

Prompt optimization is the robust held-out win. The +0.115 held-out single-agent gain is a transfer result from prompts selected on the multi-agent training composite, with a style-neutrality-validated grader as the primary metric. The multi-agent QC loop is useful but targeted; it can surface contradictions, but it also introduced a safety regression on one held-out synthetic PII case. C6 adds deterministic generated-output scrubbing to mitigate that measured failure.

## Configuration Means (All 15 Cases)

| Config | Primary composite | Rule cross-check | Holistic judge | Self-corrected | n_failed |
|---|---:|---:|---:|---:|---:|
| single baseline | 0.867 | 0.876 | 0.873 | 0.000 | 0 |
| single optimized | 0.950 | 0.950 | 0.880 | 0.000 | 0 |
| multi baseline | 0.889 | 0.898 | 0.873 | 0.000 | 0 |
| multi optimized | 0.978 | 0.961 | 0.907 | 0.200 | 0 |

Important qualifier: multi optimized is best all-case, but this includes training cases. On the held-out split, single optimized is best.

## Held-Out TEST Contrasts

| Contrast | Delta primary | Delta rule | Delta judge | n_paired | Direction |
|---|---:|---:|---:|---:|---|
| QC-loop at optimized | -0.042 | -0.042 | 0.000 | 8 | 0 up / 1 down / 7 tied |
| prompt optimization, multi | +0.073 | +0.056 | -0.037 | 8 | 2 up / 0 down / 6 tied |
| prompt optimization, single | +0.115 | +0.098 | -0.037 | 8 | 2 up / 0 down / 6 tied |
| combined worst to best | +0.073 | +0.056 | -0.037 | 8 | 2 up / 0 down / 6 tied |

## Representative Cases

- `E-CON-04`: baseline fabricated melanoma stage `pT2b`; optimized prompt correctly surfaced a missing TNM stage instead of inventing one.
- `CASE-003`: live service demo surfaces conflicting rectal-cancer stages rather than choosing one.
- `E-PII-02`: QC loop reintroduced synthetic identifiers; C6 mitigates with deterministic generated-output scrub.
