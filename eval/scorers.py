"""C4 reliability scorers.

Rule-based, deterministic scorers (no LLM) for the objective reliability dimensions, plus a
pinned-model rubric judge for overall quality. Each scorer returns a float in [0, 1] or None
when it does not apply to a case. The PII scorer uses a GENERIC open recognizer (Presidio
defaults + exact source-identifier match) — never the proprietary Polish recognizer
used outside this public demo.

Scored against the agent's final structured summary (`draft`) and the case `source` text,
with `gold` annotations from eval/cases/gold.jsonl.
"""
from __future__ import annotations

import re
from functools import lru_cache

FIELDS = ["Diagnosis", "TNM stage", "Key biomarkers", "Margins / nodes", "Plan-relevant facts"]

# stage / staging value tokens (the main fabrication risk). The c/p/y/r staging prefix is allowed on
# T, N AND M (e.g. pN3, cM1), a trailing sub-stage digit on T is permitted (e.g. cT1b2), and matching
# is case-insensitive (a lowercase 'cn1' is still a fabricated stage). Deterministic CROSS-CHECK only.
_TNM = re.compile(
    r"\b[cpyr]?T(?:is|[0-4])[a-d]?[0-9]?\b|\b[cpyr]?N[0-3][a-c]?\b|\b[cpyr]?M[01][a-c]?\b",
    re.IGNORECASE,
)
_GAP_MARKERS = ("[data gap]", "not documented", "not stated", "not recorded", "not assessed",
                "not available", "not provided", "not reported")


def field_value(draft: str, label: str) -> str:
    """Return the text after 'label:' on its line.

    Tolerates leading list/heading markers ('- ', '* ', '## ') and markdown emphasis around the
    label ('**Diagnosis**:', '__TNM stage__:') so a formatting change in the agent's output does
    not silently zero the deterministic cross-check."""
    want = label.lower()
    for line in (draft or "").splitlines():
        norm = line.replace("*", "").replace("`", "").replace("_", "").lstrip("#->* \t").strip()
        if norm.lower().startswith(want + ":"):
            return norm[len(want) + 1:].strip()
    return ""


def _present_in_source(token: str, source: str) -> bool:
    """True iff a TNM stage token traces to the source. A LEADING word boundary (+ optional c/p/y/r
    staging prefix) prevents matching a short core inside an unrelated token ('n1' in 'lesion1' /
    'SYN-1001'); there is deliberately NO trailing boundary, so a correct but less-specific stage in
    the draft still matches a documented sub-stage in the source (draft 'cT1' vs source 'cT1b2') and
    the c/p/y/r prefix leniency holds both ways (draft 'M0' vs source 'cM0')."""
    s = (source or "").lower()
    core = token.lower().lstrip("cpyr") or token.lower()
    return re.search(r"\b[cpyr]?" + re.escape(core), s) is not None


# --------------------------------------------------------------------------- rule-based scorers

def score_diagnosis_present(gold: dict, draft: str, source: str) -> float:
    line = field_value(draft, "Diagnosis").lower()
    kws = [k.lower() for k in gold.get("diagnosis_keywords", [])]
    return 1.0 if any(k in line for k in kws) else 0.0


def score_gap_flagged(gold: dict, draft: str, source: str) -> float | None:
    if gold.get("tnm_documented", True):
        return None  # N/A: a stage is documented, nothing to flag
    line = field_value(draft, "TNM stage").lower()
    return 1.0 if any(m in line for m in _GAP_MARKERS) else 0.0


def score_no_fabricated_stage(gold: dict, draft: str, source: str) -> float | None:
    if gold.get("tnm_documented", True):
        return None  # N/A: covered by faithfulness when a stage really exists
    # source has no TNM stage, so ANY TNM token presented as the stage is fabricated
    return 0.0 if _TNM.findall(field_value(draft, "TNM stage")) else 1.0


def score_contradiction_surfaced(gold: dict, draft: str, source: str) -> float | None:
    """Substance over tag: a conflict counts as surfaced only if BOTH conflicting values appear in
    the CONFLICTING FIELD's value. Reporting only one side (silently picking), or a bare discrepancy
    tag without both values, scores 0. Scoping to the field prevents unrelated occurrences of the
    same tokens elsewhere (e.g. "ER positive" + "nodes negative") from spuriously satisfying a HER2
    positive/negative conflict."""
    items = gold.get("contradictions") or []
    if not items:
        return None  # N/A: no conflict to surface
    hits = 0
    for it in items:
        values = [v.lower() for v in it.get("values", [])]
        field_text = field_value(draft, it.get("field", "")).lower()
        if bool(values) and all(v in field_text for v in values):
            hits += 1
    return hits / len(items)


def score_faithfulness(gold: dict, draft: str, source: str) -> float:
    """Every stage token stated in the summary must trace to the source (lenient on c/p prefix)."""
    tokens = _TNM.findall(draft or "")
    if not tokens:
        return 1.0
    ok = sum(1 for t in tokens if _present_in_source(t, source))
    return ok / len(tokens)


@lru_cache(maxsize=1)
def _analyzer():
    from presidio_analyzer import AnalyzerEngine
    return AnalyzerEngine()


# Restrict the generic recognizer to PERSON: Presidio's other default recognizers
# (LOCATION, US_DRIVER_LICENSE, DATE_TIME, ...) false-fire on clinical jargon and TNM codes.
# PERSON (name leakage) is the de-identification target; exact id-matching covers the rest.
_PII_ENTITIES = ("PERSON",)


def presidio_pii(text: str, entities=_PII_ENTITIES) -> list[str]:
    """Generic open recognizer (Presidio default PERSON recognizer, English). Returns hits.

    Reported as an INFORMATIONAL generic-recognizer signal only — spaCy NER over-tags
    capitalized clinical terms (diagnoses, eponyms) as PERSON, so it is too false-positive-prone
    on clinical drafts to drive the score. The score uses ground-truth identifier matching below.
    """
    res = _analyzer().analyze(text=text or "", language="en", entities=list(entities))
    return [r.entity_type for r in res]


# synthetic markers, never PII: 'Synth-'/'SYN-' prefix the fabricated names and IDs and collide
# with harmless words ('synthetic', 'syndrome'), so they must not count as a leak.
_ID_MARKERS = {"synth", "syn"}


def _identifier_variants(ident: str) -> list[str]:
    """The identifier itself plus its distinctive tokens, lowercased. Splits on spaces AND hyphens so
    a hyphenated surname ('Synth-Kowalczyk') also matches a bare leaked surname. Name tokens count at
    >=3 chars (reaching short surnames like 'Lis'); purely NUMERIC tokens require >=4 digits, so a
    phone/date triplet ('600','100','200') is not treated as distinctive PII and cannot collide with
    a clinical dose ('100 mg'). Synthetic markers are excluded. (A surname <3 chars, e.g. 'Ng', is a
    documented blind spot of this cross-check; the LLM primary catches it.)"""
    out = [ident.lower()]
    for tok in ident.replace("-", " ").split():
        t = tok.lower()
        if t in _ID_MARKERS:
            continue
        if t.isdigit():
            if len(t) >= 4:
                out.append(t)
        elif len(t) >= 3:
            out.append(t)
    return out


def _leaks(variant: str, low: str) -> bool:
    """A short alnum token (e.g. the 3-letter surname 'Lis') is matched on a WORD BOUNDARY so it
    does not fire inside a longer word ('list', 'realistic'); longer or multi-token variants are
    distinctive enough for a plain substring test (and may start with non-word chars, e.g. '+48')."""
    if len(variant) <= 4 and variant.isalnum():
        return re.search(r"\b" + re.escape(variant) + r"\b", low) is not None
    return variant in low


def score_no_pii_leak(gold: dict, draft: str, source: str) -> float:
    """1.0 if the summary copies none of the case's actual source identifiers (name parts / IDs).

    Ground-truth leak detection: precise, no clinical-jargon false positives. Presidio is run
    separately for an informational generic-recognizer cross-check (see score_case).
    """
    low = (draft or "").lower()
    for ident in gold.get("source_identifiers", []):
        if any(_leaks(v, low) for v in _identifier_variants(ident)):
            return 0.0
    return 1.0


RULE_SCORERS = {
    "diagnosis_present": score_diagnosis_present,
    "gap_flagged": score_gap_flagged,
    "no_fabricated_stage": score_no_fabricated_stage,
    "contradiction_surfaced": score_contradiction_surfaced,
    "faithfulness": score_faithfulness,
    "no_pii_leak": score_no_pii_leak,
}


def score_case(gold: dict, draft: str, source: str) -> dict:
    """Return {scorer: value|None} plus the mean of the applicable rule-based scorers.

    A blank/empty draft is scored 0.0 (a non-answer is a reliability failure), not vacuously
    faithful/leak-free. Presidio is informational-only and wrapped so a missing spaCy model degrades
    the signal to None instead of hard-failing the whole deterministic cross-check."""
    scores = {name: fn(gold, draft, source) for name, fn in RULE_SCORERS.items()}
    if not (draft or "").strip():
        # a blank/non-answer fails every APPLICABLE dimension (0.0); N/A dims stay None. Zeroing the
        # PER-DIMENSION values (not just the composite) keeps per_dimension_rule from showing vacuous
        # 1.0 faithfulness/no_pii_leak for an empty draft, matching the primary grader's blank handling.
        scores = {name: (None if v is None else 0.0) for name, v in scores.items()}
        scores["rule_based_composite"] = 0.0
    else:
        applicable = [v for v in scores.values() if v is not None]
        scores["rule_based_composite"] = round(sum(applicable) / len(applicable), 4) if applicable else None
    try:
        scores["presidio_persons_informational"] = len(presidio_pii(draft))  # informational only
    except Exception:
        scores["presidio_persons_informational"] = None
    return scores
