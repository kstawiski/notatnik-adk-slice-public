# Grounding corpus — NCI PDQ® (public-domain prose only)

This directory holds the **grounding knowledge base** for the agent's evidence step
(`retrieve_guideline`). It is built from **NCI PDQ® Health-Professional cancer-treatment
summaries**. PDQ *prose* is a work of the U.S. federal government and is in the **public
domain** — free to reproduce and redistribute, including inside this publicly-released artifact.

- `corpus/<slug>.txt` — one cleaned plain-text summary per cancer type (13 docs).
- `manifest.json` — per-document `id`, `title`, source `url`, NCI `updated` date, char count, and `sha256` (of the cleaned file).
- `pdq_index.npz` / `pdq_index_meta.jsonl` — the committed embeddings index (ships in the image).

## Copyright cleaning (important)
PDQ pages **embed third-party copyrighted material that NCI reuses *with permission*** and that
we may **not** redistribute: **AJCC TNM staging tables** ("Reprinted with permission from AJCC …
*AJCC Cancer Staging Manual*, 8th ed., Springer, 2017"), SEER/journal data tables, journal/anatomy
**figure captions**, and the `Enlarge` **image placeholders** (the images themselves are "used with
permission of the author(s), artist, and/or publisher"). `clean_corpus.py` drops any block that is
(a) tabular, (b) a `Figure N.`/`Table N.` caption line or an `Enlarge` image placeholder (matched
per line, so a two-line `Enlarge\nFigure 1. …` block is caught), or (c) carries a permission/
copyright marker — including the PDQ "Permission to Use This Summary" image-permission boilerplate.
Only public-domain PDQ prose remains. `build_index.py` shares that exact check (`has_ip_markers`)
and **fails closed** if any chunk still carries a marker or caption before embedding. The raw scrape
is kept gitignored under `pdq_raw/` and is **never** committed.

Reproduce:
```
python3 grounding/clean_corpus.py                        # pdq_raw/corpus_raw -> corpus + manifest
GOOGLE_CLOUD_PROJECT=… GOOGLE_CLOUD_LOCATION=global \
  python3 grounding/build_index.py                       # corpus -> committed index
```

## Provenance
Retrieved **2026-06-04** from `https://www.cancer.gov/types/<cancer>/hp/<slug>-pdq`
(the Health-Professional version), extracting the `#cgvBody` article container. Exact source
URLs and the NCI "Updated" date for each document are recorded in `manifest.json`. PDQ prose is
reproduced **with copyrighted tables/figures/captions and image-permission boilerplate removed**;
the cleaner strips those *lines* and drops tabular blocks, so public-domain prose adjacent to a
figure (e.g. the melanoma ABCDE criteria) is preserved (whitespace otherwise normalized).

## Coverage
Breast, prostate, rectal, colon, pancreatic, bladder (MIBC), non-small-cell lung, melanoma,
Merkel-cell, vulvar, ovarian-epithelial / **fallopian-tube** / primary-peritoneal, renal-cell,
and lip & oral cavity — chosen to cover the cancers represented in the synthetic evaluation cases.

## How grounding runs in the judged artifact
The judged Cloud Run is self-contained: **patient data is synthetic** (`MOCK_MODE=true`) while
**guideline grounding is real** (`GROUNDING_PDQ=1`) — the two axes are independent
(`tools/data_tools.py`). The embeddings index ships in the image; a grounded query makes up to two
Vertex calls (Vertex is already used for reasoning): a pinned-model **disease-gate classifier**,
then — only if it matches a document — the embedding lookup. Retrieval is **honest-miss**: a query
for a cancer outside this corpus, or pure noise, returns no citation rather than an off-topic one.
The disease gate (`classify_cancer`) classifies the query's *primary* cancer (tissue of origin —
**not** a metastatic site, an organ merely invaded by another primary, a site of prior surgery, or a
different histologic subtype) to one of the 13 docs or `none`; passages are then returned **only**
from that document and only above the cosine floor. A blank query abstains before any model call.
The gate is a classifier (not lexical) by necessity: the in/out-of-corpus cosine bands overlap, and
a lexical rule cannot separate a primary diagnosis from an out-of-corpus cancer that merely names a
shared organ/procedure/histology ("cervical cancer invading the colon", "gastric cancer after
hemicolectomy", "uterine high-grade serous") — so the gate is biased to safe abstention; see
`retriever.py`. In real-grounding mode a missing index or a transient Vertex/classifier error also
returns `[]` (an honest miss), never the synthetic stub — a fake citation is worse than none. (The
two env flags are set in the Cloud Run service definition built in C6.)

## Attribution & licensing
PDQ® is a registered trademark of the U.S. Department of Health and Human Services. The National
Cancer Institute does **not** endorse this project. Source: National Cancer Institute, PDQ®
Cancer Information Summaries (Health Professional Version), cancer.gov. NCI reuse policy:
https://www.cancer.gov/policies/copyright-reuse (PDQ text is free to reuse *unless otherwise
indicated*; the otherwise-indicated tables/figures are the blocks removed above).

## Why PDQ and not NCCN
NCCN Guidelines are **copyrighted** and may not be redistributed or embedded in a third-party
product/service without a paid NCCN content-licensing agreement, so they **cannot ship** in this
public artifact. PDQ prose is the authoritative, redistribution-safe alternative. (NCCN may still
be used privately for internal benchmarking only — never committed here.)
