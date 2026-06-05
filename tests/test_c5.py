#!/usr/bin/env python3
"""C5 tests — guideline grounding (NCI PDQ real-retrieval path), fully offline.

The committed C2 tests only exercise the synthetic stub, and `retrieve_guideline` silently falls
back to the stub on any retriever error — so a real-mode regression (no abstention, disease-gate
break, schema drift) could pass C2 unnoticed. These tests monkeypatch the index + embeddings so the
real `retriever.retrieve` and the real-mode `data_tools.retrieve_guideline` run deterministically
with NO network call.

PASS criteria:
  - honest miss: out-of-corpus cancer / pure noise / k<=0 -> [] (matches the stub no-match contract);
  - disease gate: a high-cosine hit for the WRONG cancer is not returned;
  - on-topic in-corpus query -> hit with the full citation schema;
  - stub and real `retrieve_guideline` expose an identical key set.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from grounding import retriever  # noqa: E402

# Tiny orthonormal fake index: two cancers.
_METAS = [
    {"doc_id": "rectal-treatment", "title": "Rectal Cancer Treatment", "url": "https://x/rectal",
     "section": "Neoadjuvant", "text": "cT3 rectal cancer: neoadjuvant chemoradiotherapy."},
    {"doc_id": "breast-treatment", "title": "Breast Cancer Treatment", "url": "https://x/breast",
     "section": "Adjuvant", "text": "ER-positive breast cancer: adjuvant endocrine therapy."},
]
_MAT = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype="float32")  # already unit-normalized

# Query -> embedding, chosen to drive cosine deterministically.
_QVEC = {
    "rectal ct3 neoadjuvant": [1.0, 0.0],          # cosine 1.0 with rectal
    "er-positive breast adjuvant": [0.0, 1.0],     # cosine 1.0 with breast
    "gastric cancer treatment": [0.95, 0.05],      # cosine .95 with rectal (>floor) but out-of-corpus
    "zzz nonexistent": [0.5, 0.5],                 # noise
}
# Pinned-model gate result (what the real classify_cancer would return), mocked for offline determinism.
_CLS = {
    "rectal ct3 neoadjuvant": "rectal-treatment",
    "er-positive breast adjuvant": "breast-treatment",
    "gastric cancer treatment": None,              # primary cancer not in corpus -> honest miss
    "zzz nonexistent": None,                        # noise -> honest miss
}


def test_retriever_offline() -> None:
    orig = retriever._load_index, retriever.embed_query, retriever.classify_cancer
    try:
        retriever._load_index = lambda: (_MAT, _METAS)          # bypass disk
        retriever.embed_query = lambda q: _QVEC[q.lower()]       # bypass Vertex embed
        retriever.classify_cancer = lambda q: _CLS[q.lower()]    # bypass Vertex classify gate

        # in-corpus: the classified doc's top passage is returned with the full citation schema
        hits = retriever.retrieve("rectal ct3 neoadjuvant", k=3)
        assert len(hits) == 1 and hits[0]["id"] == "rectal-treatment", hits
        assert set(hits[0]) == {"id", "source", "section", "snippet", "url", "score"}, hits[0]
        assert hits[0]["score"] >= retriever.SCORE_FLOOR
        assert retriever.retrieve("er-positive breast adjuvant", k=3)[0]["id"] == "breast-treatment"

        # gate classifies the primary cancer as out-of-corpus -> honest miss (even at high cosine)
        assert retriever.retrieve("gastric cancer treatment", k=3) == [], "out-of-corpus must abstain"
        assert retriever.retrieve("zzz nonexistent", k=3) == [], "noise must abstain"
        # k<=0 clamps to [] (no negative-slice surprise)
        assert retriever.retrieve("rectal ct3 neoadjuvant", k=0) == [], "k=0 must be empty"
        assert retriever.retrieve("rectal ct3 neoadjuvant", k=-1) == [], "k<0 must be empty"
        print("  retriever gate (classify->filter) honest-miss + k-clamp: PASS")
    finally:
        retriever._load_index, retriever.embed_query, retriever.classify_cancer = orig


def test_gate_filters_wrong_doc() -> None:
    """A passage is returned ONLY from the classified primary-cancer document: a high-cosine chunk
    from a different doc is filtered, and if the classified doc has no chunk above the floor -> []."""
    orig = retriever._load_index, retriever.embed_query, retriever.classify_cancer
    try:
        retriever._load_index = lambda: (_MAT, _METAS)
        retriever.embed_query = lambda q: [1.0, 0.0]            # points at the RECTAL chunk
        retriever.classify_cancer = lambda q: "breast-treatment"  # but gate says BREAST
        # the only over-floor chunk is rectal (wrong doc) -> filtered; no breast chunk clears floor -> []
        assert retriever.retrieve("ambiguous probe", k=3) == [], "must not return a non-classified doc"
        print("  gate returns only the classified doc's passages: PASS")
    finally:
        retriever._load_index, retriever.embed_query, retriever.classify_cancer = orig


def test_blank_query_abstains_without_model_call() -> None:
    """An empty/whitespace diagnosis must abstain (honest miss) and must NOT reach the model:
    given a blank query the model confabulates a diagnosis (observed: invents a breast cancer)
    and would yield a spurious citation. The guard short-circuits before any Vertex call."""
    orig_client = retriever._client
    try:
        def _boom():
            raise AssertionError("classify_cancer reached the model on a blank query")
        retriever._client = _boom
        assert retriever.classify_cancer("") is None
        assert retriever.classify_cancer("   ") is None
        print("  blank query abstains before any model call: PASS")
    finally:
        retriever._client = orig_client
        retriever.classify_cancer.cache_clear()


class _FakeResp:
    def __init__(self, text): self.text = text


class _FakeClient:
    """Minimal stand-in for genai.Client: .models.generate_content(...) returns a fixed text."""
    def __init__(self, text):
        self.text = text
        self.models = self

    def generate_content(self, **_):
        return _FakeResp(self.text)


def test_classify_parse_contract() -> None:
    """Lock the classifier answer-parse OFFLINE (the real prompt/parse is otherwise only covered by
    the ADC-dependent live sweep): accept exactly one doc_id token, else abstain. Hardens against a
    verbose/malformed/injected answer mis-mapping (R7 Codex+Claude caveat)."""
    orig_client = retriever._client
    try:
        cases = [
            ("nsclc-treatment", "nsclc-treatment"),                       # bare id (the contract)
            ("  NONE  ", None),                                            # bare none, case/space
            ("`breast-treatment`", "breast-treatment"),                   # markdown-wrapped id
            ("The primary is colon-treatment.", "colon-treatment"),       # prose + exactly one id
            ("could be breast-treatment or colon-treatment", None),       # ambiguous -> abstain
            ("I cannot determine the primary cancer", None),              # no id -> abstain
        ]
        for i, (raw, expected) in enumerate(cases):
            retriever._client = lambda raw=raw: _FakeClient(raw)
            retriever.classify_cancer.cache_clear()
            got = retriever.classify_cancer(f"parse-probe-{i}")  # distinct query; FakeClient ignores it
            assert got == expected, (raw, got, expected)
        print("  classify_cancer parse contract (bare/none/markdown/prose/ambiguous): PASS")
    finally:
        retriever._client = orig_client
        retriever.classify_cancer.cache_clear()


def test_retrieve_guideline_schema_parity() -> None:
    from tools import data_tools as dt

    orig = retriever.index_available, retriever.retrieve
    env = {k: os.environ.get(k) for k in ("GROUNDING_PDQ", "MOCK_MODE")}
    try:
        # Real path: index available + a canned hit; force real mode.
        retriever.index_available = lambda: True
        retriever.retrieve = lambda q, k=3: [
            {"id": "rectal-treatment", "source": "Rectal Cancer Treatment", "section": "Neoadjuvant",
             "snippet": "cT3 rectal cancer: neoadjuvant chemoradiotherapy.", "url": "https://x/rectal", "score": 0.81}
        ]
        os.environ["GROUNDING_PDQ"] = "1"
        real = dt.retrieve_guideline("rectal cT3", k=1)
        assert real and real[0]["id"] == "rectal-treatment" and "citation" in real[0], real

        # Stub path: no grounding.
        os.environ["GROUNDING_PDQ"] = "0"
        os.environ["MOCK_MODE"] = "true"
        stub = dt.retrieve_guideline("rectal t3 staging", k=1)
        assert stub and "citation" in stub[0], stub

        assert set(real[0]) == set(stub[0]), f"schema drift: real={set(real[0])} stub={set(stub[0])}"
        print("  retrieve_guideline real/stub schema parity: PASS")
    finally:
        retriever.index_available, retriever.retrieve = orig
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_clean_corpus_line_level() -> None:
    """Pin the line-level copyright cleaning: drop caption/Enlarge/permission/tab lines, keep
    public-domain prose adjacent to a figure (regression lock for R2/R3 over-/under-removal)."""
    from grounding import clean_corpus as cc

    # has_ip_markers flags taint (tab, caption, placeholder, permission), not benign prose
    assert cc.has_ip_markers("a\tb")                                  # tabular residue
    assert cc.has_ip_markers("Figure 1. Anatomy of the breast.")      # figure caption line
    assert cc.has_ip_markers("Enlarge")                               # image placeholder line
    assert cc.has_ip_markers("Images ... used with permission of the author(s).")
    assert not cc.has_ip_markers("Table 7 describes the chemotherapy regimens.")  # narrative prose
    assert not cc.has_ip_markers("Neoadjuvant chemoradiotherapy is standard.")
    # clean_block keeps prose, drops the Enlarge placeholder + its caption + the Figure caption
    out = cc.clean_block("Asymmetry of the lesion.\nBorder irregularity.\nEnlarge\n"
                         "Figure 2. Melanomas with characteristic asymmetry.\nDiagnosis")
    assert "Asymmetry of the lesion." in out and "Border irregularity." in out
    assert "Diagnosis" in out
    assert "Enlarge" not in out and "Figure 2" not in out
    # Enlarge takes the following (non-Figure) image caption line with it, keeps the heading after
    assert cc.clean_block("Enlarge\nAnatomy of the male urinary system.\nHistopathology") == "Histopathology"
    print("  clean_corpus line-level (prose kept; captions/placeholders/tabs dropped): PASS")


def main() -> int:
    print("C5 tests:")
    test_retriever_offline()
    test_gate_filters_wrong_doc()
    test_blank_query_abstains_without_model_call()
    test_classify_parse_contract()
    test_retrieve_guideline_schema_parity()
    test_clean_corpus_line_level()
    print("\nC5 GREEN — classifier-gated honest-miss + doc filtering + schema parity + cleaning (offline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
