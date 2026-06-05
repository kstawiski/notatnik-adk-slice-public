"""Derive the committed, redistribution-safe `corpus/` from the raw PDQ snapshot.

NCI PDQ prose is U.S.-government public domain, but the scraped Health-Professional pages embed
third-party copyrighted material that NCI reuses *with permission* and that we may NOT
redistribute: AJCC TNM staging tables ("Reprinted with permission from AJCC ... Springer, 2017"),
SEER/journal data tables, journal/anatomy figure captions, and the `Enlarge` image placeholders
(the images are "used with permission of the author(s), artist, and/or publisher"). This step
removes those blocks — plus the PDQ "Permission to Use This Summary" image-permission boilerplate —
so only public-domain PDQ prose ships in the public artifact (and in the embeddings index).

Pipeline (reproducible, idempotent):
  pdq_raw/corpus_raw/<slug>.txt   (gitignored; raw scrape, may contain copyrighted blocks)
     -> clean_body()             (drop tabular / caption / rights-marked blocks)
  corpus/<slug>.txt              (committed; public-domain prose only)
  manifest.json                  (chars + sha256 recomputed for the cleaned files)

Run:  python grounding/clean_corpus.py
Fails closed: aborts if any rights marker survives in the cleaned corpus.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "pdq_raw" / "corpus_raw"   # gitignored raw snapshot
CORPUS = HERE / "corpus"                # committed, cleaned
MANIFEST = HERE / "manifest.json"

# Markers of non-public-domain (copyrighted, permission-only) third-party content, plus the PDQ
# image-permission boilerplate ("...used with permission of the author(s)..." / the "Permission to
# Use This Summary" section) — the images those captions describe are NOT redistributable.
IP_MARKER_RE = re.compile(
    r"reprinted with permission|reprinted from|all rights reserved|with permission from"
    r"|used with permission|permission to use this summary"
    r"|amin mb,|edge sb,|ajcc cancer staging manual|\bspringer\b|albores-saavedra|©",
    re.I,
)
# Figure/table caption lines and `Enlarge` image placeholders (the copyrighted graphics live here).
# Matched per-LINE (not just block-start) so a two-line `Enlarge\nFigure 1. ...` block is caught.
# `Table \d+\.` requires the trailing period so narrative prose ("Table 7 describes ...") is kept.
_CAPTION_LINE_RE = re.compile(r"^(Enlarge$|Figure \d|Table \d+\.)")


def has_ip_markers(text: str) -> bool:
    """True if `text` still carries a copyright/permission marker, a figure/table caption /
    `Enlarge` image-placeholder line, OR a tab (tabular table residue). Single source of truth for
    both the cleaner's fail-closed residual check and build_index.py's pre-embedding guard."""
    if "\t" in text or IP_MARKER_RE.search(text):
        return True
    return any(_CAPTION_LINE_RE.match(ln.strip()) for ln in text.splitlines())


def clean_block(block: str) -> str:
    """Remove only the caption / `Enlarge` placeholder / permission-marker LINES from a block,
    keeping the public-domain prose lines around them (e.g. the melanoma ABCDE bullets that share a
    block with a Figure caption — dropping the whole block would lose that public-domain prose). An
    `Enlarge` placeholder also takes the following line — the image caption, which need not start
    with 'Figure' — with it."""
    out, drop_next = [], False
    for ln in block.split("\n"):
        if drop_next:
            drop_next = False
            continue  # the image caption line that follows an `Enlarge` placeholder
        s = ln.strip()
        if s == "Enlarge":
            drop_next = True
            continue
        if _CAPTION_LINE_RE.match(s) or IP_MARKER_RE.search(s):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _split_header(text: str) -> tuple[str, str]:
    """Return (provenance_header, body). The header runs through the RETRIEVED: line."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("RETRIEVED:"):
            return "\n".join(lines[: i + 1]), "\n".join(lines[i + 1 :]).strip()
    return "", text.strip()


def clean_body(body: str) -> str:
    """Keep public-domain prose; drop tabular blocks whole and strip caption/placeholder/marker
    lines from the rest, so prose adjacent to a figure is preserved rather than removed with it."""
    kept = []
    for b in re.split(r"\n\s*\n", body):
        if not b.strip() or "\t" in b:
            continue  # blank, or a tabular block (AJCC/SEER table) -> drop entirely
        cleaned = clean_block(b)
        if cleaned:
            kept.append(cleaned)
    return "\n\n".join(kept)


def clean_text(text: str) -> str:
    header, body = _split_header(text)
    cleaned = clean_body(body)
    return f"{header}\n\n{cleaned}\n" if header else f"{cleaned}\n"


def main() -> int:
    if not RAW.is_dir():
        raise SystemExit(f"raw snapshot missing: {RAW} (expected the gitignored pre-clean corpus)")
    manifest = {m["id"]: m for m in json.loads(MANIFEST.read_text(encoding="utf-8"))}
    CORPUS.mkdir(exist_ok=True)
    new_manifest: list[dict] = []
    total_removed = 0
    for raw_path in sorted(RAW.glob("*.txt")):
        doc_id = raw_path.stem
        raw = raw_path.read_text(encoding="utf-8")
        cleaned = clean_text(raw)
        removed = len(raw) - len(cleaned)
        total_removed += removed
        out = CORPUS / f"{doc_id}.txt"
        out.write_text(cleaned, encoding="utf-8")
        raw_bytes = out.read_bytes()
        meta = dict(manifest.get(doc_id, {"id": doc_id, "title": doc_id, "url": "", "updated": ""}))
        meta["id"] = doc_id
        meta["chars"] = len(cleaned)
        meta["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        new_manifest.append(meta)
        print(f"  {doc_id:32s} -{removed:>7d} chars -> {len(cleaned):>7d}")
    MANIFEST.write_text(json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Fail closed: no copyright/permission marker or figure/table/image caption may survive.
    residual = []
    for p in sorted(CORPUS.glob("*.txt")):
        for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if has_ip_markers(ln):
                residual.append(f"{p.name}:{n}: {ln[:90]}")
    if residual:
        print("\nRESIDUAL IP MARKERS (cleaning incomplete):", file=sys.stderr)
        print("\n".join(residual), file=sys.stderr)
        raise SystemExit(1)
    print(f"\ncleaned {len(new_manifest)} docs, removed {total_removed} chars; 0 residual IP markers; manifest rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
