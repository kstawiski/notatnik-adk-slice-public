"""Runtime safety post-processing for the public synthetic demo.

This is deliberately generic and non-proprietary: it extracts obvious synthetic names and
identifier values from the case source, then redacts those terms from generated text. It is
not the private Polish recognizer stack from Notatnik.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

REDACTION = "[REDACTED]"

_NAME_RE = re.compile(
    r"(?:^|[\[\]\n,.;:]\s*)(?:Patient(?:\s+Name)?|Name)\s*:?\s+"
    r"([A-Z][^\d,.;()\n]+?)(?=(?:[,.;()\n]|\s+(?:ID|MRN|DOB|National\s+ID|Phone)\b|$))"
)
_ID_RE = re.compile(
    r"(?:^|[\[\]\(\)\n,.;:]\s*)(?:Patient\s+ID|National\s+ID|MRN|ID)\s*:?\s*"
    r"([A-Z]{2,6}-?\d{3,}|\d{4,})\b",
    re.IGNORECASE,
)
_DOB_RE = re.compile(r"\bDOB\s*:?\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(\+\d{1,3}(?:[\s-]?\d{2,4}){2,5})")
_LABEL_VALUE_RE = re.compile(
    r"\b(Patient Name|Patient ID|MRN|National ID|DOB|Phone)\s*:\s*([^\n]+)", re.IGNORECASE
)
_REDACTED_PAREN_RE = re.compile(
    r"\s*\([^()\n]*(?:Patient|Name|MRN|National ID|DOB|Phone|ID)\s*:\s*"
    + re.escape(REDACTION)
    + r"[^()\n]*\)?",
    re.IGNORECASE,
)
_REDACTED_ONLY_LINE_RE = re.compile(
    r"(?im)^\s*(?:Patient Name|Patient|Name|MRN|National ID|DOB|Phone|ID)\s*:\s*"
    + re.escape(REDACTION)
    + r"\s*$\n?"
)
_TOKEN_SPLIT_RE = re.compile(r"[\s\-]+")
_NOISE_TOKENS = {
    "patient",
    "name",
    "id",
    "mrn",
    "dob",
    "national",
    "phone",
    "synth",
    "syn",
    "test",
}


def sensitive_terms_from_source(source: str) -> set[str]:
    """Extract obvious source identifiers without private PHI recognizers."""
    terms: set[str] = set()
    for regex in (_NAME_RE, _ID_RE, _DOB_RE, _PHONE_RE):
        for match in regex.findall(source or ""):
            value = match if isinstance(match, str) else match[0]
            _add_identifier_terms(terms, value)
    return terms


def scrub_text(text: str, source: str | None = None, *, extra_terms: set[str] | None = None) -> str:
    """Redact source identifiers and generic label values from generated text."""
    out = text or ""
    terms = set(extra_terms or set())
    if source:
        terms |= sensitive_terms_from_source(source)

    out = _LABEL_VALUE_RE.sub(lambda m: f"{m.group(1)}: {REDACTION}", out)
    for term in sorted(terms, key=len, reverse=True):
        if not term:
            continue
        pattern = re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", re.IGNORECASE)
        out = pattern.sub(REDACTION, out)
    out = _REDACTED_PAREN_RE.sub("", out)
    out = _REDACTED_ONLY_LINE_RE.sub("", out)
    return out


def scrub_obj(value: object, source: str | None = None, *, extra_terms: set[str] | None = None) -> object:
    """Recursively redact source identifiers from JSON-like values."""
    if isinstance(value, str):
        return scrub_text(value, source, extra_terms=extra_terms)
    if isinstance(value, Mapping):
        return {k: scrub_obj(v, source, extra_terms=extra_terms) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_obj(v, source, extra_terms=extra_terms) for v in value]
    if isinstance(value, tuple):
        return tuple(scrub_obj(v, source, extra_terms=extra_terms) for v in value)
    return value


def scrub_mapping(values: Mapping[str, object], source: str | None = None) -> dict[str, object]:
    """Return a recursively redacted dict copy."""
    return {k: scrub_obj(v, source) for k, v in values.items()}


def contains_sensitive_term(text: str, terms: set[str]) -> bool:
    """True when any source-derived sensitive term remains as a standalone token/phrase."""
    for term in sorted(terms, key=len, reverse=True):
        if not term or len(term) < 3:
            continue
        pattern = re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", re.IGNORECASE)
        if pattern.search(text or ""):
            return True
    return False


def _add_identifier_terms(terms: set[str], value: str) -> None:
    ident = " ".join((value or "").strip().split())
    if not ident:
        return
    terms.add(ident)
    has_alpha = any(ch.isalpha() for ch in ident)
    for token in _TOKEN_SPLIT_RE.split(ident):
        tok = token.strip(".,;:()[]{}")
        low = tok.lower()
        if low in _NOISE_TOKENS:
            continue
        if tok.isdigit():
            if len(tok) >= 4 and not has_alpha:
                terms.add(tok)
        elif len(tok) >= 3:
            terms.add(tok)
