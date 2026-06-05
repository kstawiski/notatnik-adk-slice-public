"""Local Vertex-embeddings retrieval over the NCI PDQ grounding corpus.

Self-contained grounding for `retrieve_guideline`: a COMMITTED embeddings index (built by
`build_index.py` from `grounding/corpus/`) plus ONE pinned Vertex embedding call per query.
No Discovery Engine / no external datastore — the index ships inside the image, and the only
network call is to Vertex (which the agent already uses for reasoning). Deterministic given the
pinned embedding model, so the judged Cloud Run stays self-contained and reproducible.

The embedding model is pinned (`EMBED_MODEL`). The corpus and agent queries are English, so the
English `text-embedding-005` model is used (the multilingual variant would only dilute it).
"""
from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

EMBED_MODEL = "text-embedding-005"  # pinned (English, 768-dim); bump deliberately + rebuild index
VEC_PATH = _HERE / "pdq_index.npz"
META_PATH = _HERE / "pdq_index_meta.jsonl"

# Abstention floor (cosine). Below this, even the nearest passage is noise — return nothing
# rather than an off-topic citation. Calibrated on the committed index: in-corpus queries score
# >=0.70, pure-noise queries ~0.45; 0.60 clears noise with margin without dropping real hits.
SCORE_FLOOR = 0.60

# Disease gate (pinned-model classifier). The 13-doc corpus covers specific cancers, and
# semantically-adjacent OUT-of-corpus cancers (gastric, cervical, thyroid, lymphoma, uterine serous,
# small-cell lung, ...) embed too close to in-corpus lows for a cosine floor to separate. A lexical
# gate also cannot distinguish a PRIMARY diagnosis ("colon adenocarcinoma") from an out-of-corpus
# cancer that merely names a shared site / procedure / histology ("cervical cancer invading the
# colon", "gastric cancer after hemicolectomy", "uterine high-grade serous"). So the gate asks the
# pinned reasoning model to classify the query's PRIMARY cancer (tissue of origin — NOT a metastatic
# site, an invaded organ, prior surgery, or a different subtype) to one of the 13 docs, or "none".
# Out-of-corpus -> honest miss. One classify call per query (temp 0; cached per query string) — as
# reproducible as a model classifier gets. The C4 eval uses the synthetic stub, NOT this path, so eval
# reproducibility is unaffected; the live demo uses it. A classifier transport error propagates to
# retrieve_guideline, which returns [] (honest miss) — never an off-topic stub citation.

# Human-readable primary-cancer label per doc, shown to the classifier (negatives pin the known traps).
_DOC_LABELS: dict[str, str] = {
    "bladder-treatment": "bladder cancer (urothelial carcinoma of the bladder)",
    "breast-treatment": "breast cancer",
    "colon-treatment": "colon cancer (colon adenocarcinoma)",
    "lip-oral-cavity-treatment": "lip or oral cavity cancer",
    "melanoma-treatment": "melanoma (cutaneous or mucosal)",
    "merkel-cell-treatment": "Merkel cell carcinoma",
    "nsclc-treatment": "non-small cell lung cancer (NSCLC); NOT small cell lung cancer",
    "ovarian-epithelial-treatment": "epithelial ovarian, fallopian tube, or primary peritoneal cancer; NOT uterine/endometrial",
    "pancreatic-treatment": "pancreatic cancer (pancreatic ductal adenocarcinoma)",
    "prostate-treatment": "prostate cancer",
    "rectal-treatment": "rectal cancer (rectal adenocarcinoma)",
    "renal-cell-treatment": "renal cell carcinoma / kidney cancer; NOT nephroblastoma or adrenal cancer",
    "vulvar-treatment": "vulvar cancer",
}

_GATE_INSTRUCTION = (
    "You classify the PRIMARY cancer in a clinical diagnosis, to select the correct treatment "
    "guideline. The PRIMARY cancer is the TISSUE OF ORIGIN of the malignancy. It is NOT a metastatic "
    "site (e.g. 'pulmonary metastases' is not lung cancer), NOT an organ merely invaded or involved "
    "by another primary, NOT a site of prior surgery (e.g. 'after hemicolectomy' does not make a "
    "gastric cancer a colon cancer), and NOT a different histologic subtype than the one listed.\n\n"
    "Candidate primary cancers (id: description):\n{labels}\n\n"
    "Diagnosis: {query}\n\n"
    "Reply with EXACTLY one id from the list whose description matches the PRIMARY cancer, or the "
    "single word none if the primary cancer is not in the list. Output only the id or none."
)


@functools.lru_cache(maxsize=512)
def classify_cancer(query: str) -> str | None:
    """Classify the query's PRIMARY cancer to one of the 13 doc_ids, or None if out-of-corpus.
    Pinned model, temp 0; cached per query string. Raises on transport error (callers treat a
    raised result as an honest miss)."""
    from agents.model import MODEL_ID
    from google.genai import types

    q = (query or "").strip()
    if not q:
        return None  # blank diagnosis -> honest miss (never let the model confabulate one)
    labels = "\n".join(f"  {doc_id}: {lbl}" for doc_id, lbl in _DOC_LABELS.items())
    prompt = _GATE_INSTRUCTION.format(labels=labels, query=q)
    client = _client()  # bind to a local: the temporary Client is GC'd mid-call otherwise (closes httpx)
    resp = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )
    ans = (getattr(resp, "text", "") or "").strip().lower()
    # Parse the single-token contract robustly: split into whole tokens (keep the id's hyphens, turn
    # all other punctuation/markdown/prose into separators) and accept a doc_id ONLY if exactly one
    # appears as a standalone token. Ambiguous (>=2 ids) or absent -> None (abstain, the safe
    # direction). This avoids a substring / first-in-dict-order mis-map if the model ever wraps the
    # id in an explanation instead of emitting it bare.
    tokens = set("".join(c if (c.isalnum() or c == "-") else " " for c in ans).split())
    matches = [doc_id for doc_id in _DOC_LABELS if doc_id in tokens]
    return matches[0] if len(matches) == 1 else None


def _client():
    from agents.model import LOCATION, PROJECT, ensure_vertex_env

    ensure_vertex_env()
    from google import genai

    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION)


def embed_texts(
    texts: list[str], *, task_type: str = "RETRIEVAL_DOCUMENT", char_budget: int = 48000, max_items: int = 200
) -> list[list[float]]:
    """Embed texts on Vertex with the pinned model. task_type asymmetry improves retrieval.

    The model caps total input per request (~20k tokens), so batches are packed greedily under a
    conservative character budget (~4 chars/token -> ~12k tokens) and an instance-count cap. At
    least one text is always sent per request.
    """
    from google.genai import types

    client = _client()
    out: list[list[float]] = []
    i, n = 0, len(texts)
    while i < n:
        batch: list[str] = []
        chars = 0
        while i < n and len(batch) < max_items and (not batch or chars + len(texts[i]) <= char_budget):
            batch.append(texts[i])
            chars += len(texts[i])
            i += 1
        resp = client.models.embed_content(
            model=EMBED_MODEL, contents=batch,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        if len(resp.embeddings) != len(batch):
            raise RuntimeError(f"Vertex returned {len(resp.embeddings)} embeddings for {len(batch)} inputs")
        out.extend(e.values for e in resp.embeddings)
    return out


def embed_query(query: str) -> list[float]:
    return embed_texts([query], task_type="RETRIEVAL_QUERY")[0]


def index_available() -> bool:
    return VEC_PATH.exists() and META_PATH.exists()


@functools.lru_cache(maxsize=1)
def _load_index():
    import numpy as np

    mat = np.load(VEC_PATH)["vectors"].astype("float32")
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.clip(norms, 1e-8, None)  # L2-normalize -> dot product == cosine
    metas = [json.loads(line) for line in META_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if mat.shape[0] != len(metas):
        raise ValueError(f"index/meta length mismatch: {mat.shape[0]} vectors vs {len(metas)} metas")
    return mat, metas


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Top-k PDQ passages for a query, as citation records (cosine over the committed index).

    Honest miss by design: the pinned-model gate (classify_cancer) maps the query's PRIMARY cancer to
    one of the 13 docs or None; passages are returned ONLY from that document and only if they clear
    SCORE_FLOOR. A query whose primary cancer is outside the corpus, or pure noise, returns []
    rather than a confident off-topic citation. k<=0 returns [] (no negative-slice surprise).
    """
    import numpy as np

    if k <= 0:
        return []
    target = classify_cancer(query)
    if target is None:
        return []  # primary cancer not among the 13 docs -> honest miss (classify before embed)
    mat, metas = _load_index()
    q = np.asarray(embed_query(query), dtype="float32")
    q = q / max(float(np.linalg.norm(q)), 1e-8)
    sims = mat @ q
    out = []
    for i in np.argsort(-sims):
        score = float(sims[int(i)])
        if score < SCORE_FLOOR:
            break  # sorted descending — nothing below the floor can qualify
        m = metas[int(i)]
        if m["doc_id"] != target:
            continue  # only the classified primary cancer's document
        out.append(
            {
                "id": m["doc_id"],
                "source": m["title"],
                "section": m.get("section", ""),
                "snippet": m["text"][:500],
                "url": m["url"],
                "score": round(score, 4),
            }
        )
        if len(out) >= k:
            break
    return out
