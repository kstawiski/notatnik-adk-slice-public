"""Baseline prompts + the instruction-augmentation library for the C4 optimizer.

The BASELINE prompts are deliberately naive (a plain summarizer + a vague reviewer) — the
"before" of the optimize story. The optimizer (eval/harness.py:optimize) is a scripted
instruction-tuning loop: it measures, on the TRAIN split, which generic augmentations improve
the rule-based composite, then composes the OPTIMIZED prompts from the ones that help. All
prompts are sanitized/non-proprietary and specific to this public challenge slice.

State keys injected by ADK: {case_id}, {draft}, {qc_feedback?} (optional).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSet:
    documentation: str
    qc: str


_DOC_HEAD = """\
You are a clinical documentation assistant. The case identifier is {case_id}.
Call get_document_text with case_id="{case_id}" to read the source, then write a structured
summary with these fields, each on its own line:
- Diagnosis:
- TNM stage:
- Key biomarkers:
- Margins / nodes:
- Plan-relevant facts:"""

_DOC_TAIL = """
A reviewer may have left feedback on your previous draft (empty on the first pass):
{qc_feedback?}
If feedback is present, revise the summary to resolve every point; copy any exact line it gives.
Output only the structured summary.
"""

_QC_HEAD = """\
You are a clinical QC reviewer. The case identifier is {case_id}. Read the source with
get_document_text(case_id="{case_id}") and review this draft:
{draft}"""

_QC_TAIL = """
If the draft is acceptable, call the exit_loop tool. Otherwise, describe what should change.
"""

BASELINE_DOC = _DOC_HEAD + _DOC_TAIL
BASELINE_QC = _QC_HEAD + _QC_TAIL
BASELINE = PromptSet(documentation=BASELINE_DOC, qc=BASELINE_QC)

# --- augmentation library (each is appended to the relevant baseline prompt) -----------------
# A genuine generic prompt-engineering improvement; the optimizer keeps the ones that help on
# the train split. Targets: "doc", "qc", or "both".
AUGMENTATIONS: list[dict] = [
    {
        "name": "data_gap",
        "target": "both",
        "doc": ('\nIf a field is not documented in the source, write exactly '
                '"[DATA GAP] <field> not documented in source" — never leave a field blank.'),
        "qc": ('\nEvery field absent from the source MUST be flagged "[DATA GAP] ..."; a case '
               'with no documented TNM stage must carry an explicit TNM data-gap flag, not a '
               'blank or omission.'),
    },
    {
        "name": "no_fabricate",
        "target": "doc",
        "doc": ('\nState only values that appear in the source. Never infer, guess, or '
                'fabricate a value (especially a TNM stage that is not written in the source).'),
        "qc": "",
    },
    {
        "name": "discrepancy",
        "target": "qc",
        "doc": "",
        "qc": ('\nIf the source gives conflicting values across documents (e.g. a different '
               'T-stage in two reports), the draft must surface BOTH values (e.g. '
               '"A vs B" or both labelled by source). A draft that reports only one side of a '
               'real conflict, or silently picks one, FAILS; a draft that shows both values '
               'for the conflicting field passes this check.'),
    },
    {
        "name": "exit_discipline",
        "target": "qc",
        "doc": "",
        "qc": ('\nEnd your turn with EXACTLY ONE action: PASS = call exit_loop and output no '
               'other text; REJECT = do not call exit_loop and output a numbered list of the '
               'specific defects to fix, naming the field and the exact correction required.'),
    },
]


def compose(selected: list[str]) -> PromptSet:
    """Build a PromptSet from BASELINE plus the named augmentations (rules before the tails)."""
    doc_rules, qc_rules = "", ""
    for a in (a for a in AUGMENTATIONS if a["name"] in selected):  # library order, stable
        if a["target"] in ("doc", "both"):
            doc_rules += a["doc"]
        if a["target"] in ("qc", "both"):
            qc_rules += a["qc"]
    return PromptSet(documentation=_DOC_HEAD + doc_rules + _DOC_TAIL,
                     qc=_QC_HEAD + qc_rules + _QC_TAIL)
