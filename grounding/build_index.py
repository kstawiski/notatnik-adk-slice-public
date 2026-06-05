"""Build the committed PDQ embeddings index from grounding/corpus/*.txt.

Deterministic given the pinned embedding model (retriever.EMBED_MODEL). Run once, and again
whenever the corpus changes:

  GOOGLE_CLOUD_PROJECT=gen-lang-client-0384080704 GOOGLE_CLOUD_LOCATION=global \\
  python grounding/build_index.py

Writes (committed, ship in the image):
  pdq_index.npz        float32 [N, 768] embeddings, key "vectors"
  pdq_index_meta.jsonl one JSON object per row: {doc_id, title, url, section, text}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
MANIFEST = HERE / "manifest.json"
MAX_CHARS = 2000  # well under the embedding model's input limit; ~1 section worth of text

sys.path.insert(0, str(HERE))
import retriever  # noqa: E402  (embed_texts + paths + pinned model)


def _body(text: str) -> str:
    """Drop the provenance header (everything up to and including the RETRIEVED: line)."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("RETRIEVED:"):
            return "\n".join(lines[i + 1 :]).strip()
    return text.strip()


def _looks_like_heading(p: str) -> bool:
    # Single-line only: a multi-line block is prose, never a heading.
    return ("\n" not in p and len(p) < 80 and not p.endswith((".", ":", ";", ","))
            and p[:1].isupper() and "  " not in p)


def _hard_split(p: str, max_chars: int) -> list[str]:
    """Split an oversized paragraph on whitespace boundaries so no chunk exceeds the cap and
    no word is broken mid-token (raw character slicing corrupted edge tokens)."""
    pieces, cur = [], ""
    for w in p.split():
        if cur and len(cur) + len(w) + 1 > max_chars:
            pieces.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        pieces.append(cur)
    return pieces or [p]


def chunk_doc(text: str, max_chars: int = MAX_CHARS) -> list[tuple[str, str]]:
    """Greedy paragraph packing into <= max_chars chunks, tracking the latest single-line heading
    as the section label. Heading-like lines are KEPT in the embedded text (only used to update the
    section), because the heuristic cannot tell a true heading from a short enumerated line (e.g. a
    treatment-option bullet) — dropping them would silently lose the highest-value guideline content."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", _body(text)) if p.strip()]
    chunks: list[tuple[str, str]] = []
    cur, section = "", ""
    for p in paras:
        if _looks_like_heading(p):
            section = p  # update the section label; the line is still embedded as content below
        for piece in (_hard_split(p, max_chars) if len(p) > max_chars else [p]):
            if cur and len(cur) + len(piece) + 1 > max_chars:
                chunks.append((section, cur))
                cur = piece
            else:
                cur = f"{cur}\n{piece}".strip()
    if cur:
        chunks.append((section, cur))
    return chunks


def main() -> int:
    import numpy as np

    from clean_corpus import has_ip_markers  # single source of truth for the copyright guard

    manifest = {m["id"]: m for m in json.loads(MANIFEST.read_text(encoding="utf-8"))}
    metas: list[dict] = []
    for path in sorted(CORPUS.glob("*.txt")):
        doc_id = path.stem
        info = manifest.get(doc_id, {})
        for section, chunk in chunk_doc(path.read_text(encoding="utf-8")):
            metas.append(
                {
                    "doc_id": doc_id,
                    "title": info.get("title", doc_id),
                    "url": info.get("url", ""),
                    "section": section,
                    "text": chunk,
                }
            )

    # Fail closed: never embed copyrighted/permission-only content (markers OR figure/table/image
    # captions) into the shipped index.
    tainted = [m for m in metas if has_ip_markers(m["text"]) or has_ip_markers(m["section"])]
    if tainted:
        raise SystemExit(
            f"refusing to embed {len(tainted)} chunk(s) carrying copyright/permission markers; "
            f"re-run clean_corpus.py first (e.g. {tainted[0]['doc_id']}: {tainted[0]['text'][:80]!r})"
        )

    print(f"chunked {len(list(CORPUS.glob('*.txt')))} docs -> {len(metas)} chunks; embedding on Vertex ({retriever.EMBED_MODEL}) ...")
    vectors = retriever.embed_texts([m["text"] for m in metas], task_type="RETRIEVAL_DOCUMENT")
    arr = np.asarray(vectors, dtype="float32")
    if arr.shape[0] != len(metas):
        raise SystemExit(f"embedding count {arr.shape[0]} != chunk count {len(metas)}")

    np.savez_compressed(retriever.VEC_PATH, vectors=arr)
    with retriever.META_PATH.open("w", encoding="utf-8") as fh:
        for m in metas:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"wrote {retriever.VEC_PATH.name} {arr.shape} and {retriever.META_PATH.name} ({len(metas)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
