"""SYNTHETIC oncology fixtures — no real patient data. All names/IDs are invented.

These back the deterministic MOCK_MODE tool layer (the judged Cloud Run artifact runs entirely
on these; no private database, no private search service, no GPU). Cases are designed to exercise the reliability story:
  CASE-001  clean case, complete TNM            (baseline happy path)
  CASE-002  pathology present but TNM MISSING    (QC must catch the omission)
  CASE-003  contradictory T-stage across 2 docs  (stall -> resolve / self-correction)
"""
from __future__ import annotations

import json
from pathlib import Path

# --- synthetic source documents per case ----------------------------------------------------
SYNTH_CASES: dict[str, dict] = {
    "CASE-001": {
        "title": "Breast carcinoma — postoperative",
        "documents": [
            {
                "name": "histopathology.txt",
                "text": (
                    "[SYNTHETIC] Patient: Anna Test-Nowak, ID SYN-0001.\n"
                    "Specimen: right breast, wide local excision + sentinel node biopsy.\n"
                    "Invasive ductal carcinoma, grade 2. Tumour size 18 mm. "
                    "ER 90%, PR 80%, HER2 negative (IHC 1+), Ki-67 15%.\n"
                    "Margins clear (nearest 4 mm). Sentinel nodes 0/2 involved.\n"
                    "Staging: pT1c pN0 cM0 (AJCC 8th)."
                ),
            },
        ],
    },
    "CASE-002": {
        "title": "NSCLC — staging incomplete",
        "documents": [
            {
                "name": "bronchoscopy_path.txt",
                "text": (
                    "[SYNTHETIC] Patient: Piotr Test-Wisniewski, ID SYN-0002.\n"
                    "Endobronchial biopsy, left upper lobe: non-small cell lung carcinoma, "
                    "adenocarcinoma subtype. PD-L1 TPS 30%. EGFR/ALK pending.\n"
                    "No TNM stage documented in the available report."
                ),
            },
            {
                "name": "ct_chest.txt",
                "text": (
                    "[SYNTHETIC] CT chest: 3.4 cm spiculated mass LUL. Mediastinal nodes "
                    "not enlarged. No distant lesions on this study."
                ),
            },
        ],
    },
    "CASE-003": {
        "title": "Rectal cancer — conflicting T-stage",
        "documents": [
            {
                "name": "mri_rectum.txt",
                "text": (
                    "[SYNTHETIC] Patient: Maria Test-Lewandowska, ID SYN-0003.\n"
                    "MRI rectum: tumour 6 cm from anal verge, invading muscularis propria "
                    "without extramural spread. Staging: cT2 N0."
                ),
            },
            {
                "name": "mdt_note.txt",
                "text": (
                    "[SYNTHETIC] MDT note: rectal adenocarcinoma. Imaging reviewed; "
                    "extramural vascular invasion present, tumour through muscularis into "
                    "perirectal fat. Staging recorded as cT3 N1."
                ),
            },
        ],
    },
}

# Merge the additional SYNTHETIC C4 eval cases (source documents only) so the MCP
# get_document_text tool serves them too. Backward-compatible: if the file is absent only the
# demo cases above are served; setdefault never overwrites a demo case.
def _merge_eval_corpus() -> None:
    corpus = Path(__file__).resolve().parents[1] / "eval" / "cases" / "corpus.json"
    if corpus.exists():
        for cid, case in json.loads(corpus.read_text()).items():
            SYNTH_CASES.setdefault(cid, case)


_merge_eval_corpus()

# --- synthetic literature (PubMed-shaped) ---------------------------------------------------
_PUBMED: list[dict] = [
    {"pmid": "SYN10001", "title": "Adjuvant endocrine therapy in ER-positive early breast cancer",
     "journal": "Synth J Oncol", "year": 2024, "topics": ["breast", "er", "endocrine"],
     "snippet": "[SYNTHETIC] Adjuvant endocrine therapy reduces recurrence in ER-positive disease."},
    {"pmid": "SYN10002", "title": "PD-L1 expression and immunotherapy in advanced NSCLC",
     "journal": "Synth Lung Rev", "year": 2025, "topics": ["lung", "nsclc", "pd-l1", "immunotherapy"],
     "snippet": "[SYNTHETIC] PD-L1 TPS guides first-line checkpoint-inhibitor selection in NSCLC."},
    {"pmid": "SYN10003", "title": "Neoadjuvant chemoradiotherapy for locally advanced rectal cancer",
     "journal": "Synth Colorectal", "year": 2023, "topics": ["rectal", "rectum", "chemoradiotherapy", "t3"],
     "snippet": "[SYNTHETIC] Neoadjuvant CRT improves local control in cT3/N+ rectal cancer."},
    {"pmid": "SYN10004", "title": "Principles of TNM staging accuracy in solid tumours",
     "journal": "Synth Staging", "year": 2024, "topics": ["tnm", "staging", "quality"],
     "snippet": "[SYNTHETIC] Complete TNM documentation is prerequisite for guideline-concordant care."},
]

# --- synthetic trials (ClinicalTrials.gov-shaped) -------------------------------------------
_TRIALS: list[dict] = [
    {"nct_id": "NCT-SYN-0001", "title": "Endocrine +/- CDK4/6 in ER+ early breast cancer",
     "phase": "III", "status": "Recruiting", "conditions": ["breast", "er"],
     "snippet": "[SYNTHETIC] Randomised adjuvant trial; key eligibility ER+ HER2- pT1-3."},
    {"nct_id": "NCT-SYN-0002", "title": "First-line immunotherapy combination in PD-L1+ NSCLC",
     "phase": "II", "status": "Recruiting", "conditions": ["lung", "nsclc"],
     "snippet": "[SYNTHETIC] Eligibility: stage III-IV NSCLC, PD-L1 TPS >=1%."},
    {"nct_id": "NCT-SYN-0003", "title": "Total neoadjuvant therapy in rectal cancer",
     "phase": "III", "status": "Active", "conditions": ["rectal", "rectum"],
     "snippet": "[SYNTHETIC] Eligibility: cT3-4 or N+ rectal adenocarcinoma."},
]

# --- synthetic guideline corpus (grounding seed; full corpus indexed in C5) ------------------
SYNTH_GUIDELINES: list[dict] = [
    {"id": "SG-BR-01", "source": "SynthOnc Guideline v1", "section": "Breast / adjuvant systemic",
     "topics": ["breast", "er", "endocrine"],
     "text": "[SYNTHETIC] ER-positive early breast cancer: offer >=5 years adjuvant endocrine therapy."},
    {"id": "SG-LU-01", "source": "SynthOnc Guideline v1", "section": "Lung / staging",
     "topics": ["lung", "nsclc", "tnm", "staging"],
     "text": "[SYNTHETIC] NSCLC management requires complete TNM stage before treatment selection."},
    {"id": "SG-RE-01", "source": "SynthOnc Guideline v1", "section": "Rectal / neoadjuvant",
     "topics": ["rectal", "rectum", "t3", "staging"],
     "text": "[SYNTHETIC] cT3 or node-positive rectal cancer: recommend neoadjuvant chemoradiotherapy."},
]


def _rank(items: list[dict], query: str, k: int) -> list[dict]:
    """Deterministic keyword overlap ranking (stable: score desc, then index)."""
    q = {t for t in (query or "").lower().replace("/", " ").split() if t}
    scored = []
    for i, it in enumerate(items):
        topics = set(it.get("topics", [])) | set(it.get("conditions", []))
        hay = topics | set(str(it.get("title", "")).lower().split())
        score = len(q & hay)
        scored.append((score, -i, it))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    # No keyword overlap -> return nothing (honest miss). Never fall back to an
    # unrelated record: a clinical search must not surface off-topic citations.
    return [it for score, _, it in scored if score > 0][: max(0, k)]
