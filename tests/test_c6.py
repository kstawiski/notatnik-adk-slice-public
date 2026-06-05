#!/usr/bin/env python3
"""C6 tests — Cloud Run FastAPI surface + deterministic safety post-scrub (no Vertex calls)."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.pipeline import CaseRun  # noqa: E402
from service.main import app  # noqa: E402
from tools import data_tools  # noqa: E402
from tools.safety import contains_sensitive_term, scrub_obj, scrub_text, sensitive_terms_from_source  # noqa: E402


def test_scrub_redacts_source_identifiers_without_damaging_trial_ids() -> None:
    source = data_tools.get_document_text("CASE-002")
    terms = sensitive_terms_from_source(source)
    assert "Piotr Test-Wisniewski" in terms
    assert "SYN-0002" in terms

    text = "Patient Name: Piotr Test-Wisniewski\nID: SYN-0002\nTrial: NCT-SYN-0002"
    scrubbed = scrub_text(text, source)
    assert "Piotr" not in scrubbed
    assert "ID:" not in scrubbed
    assert "NCT-SYN-0002" in scrubbed, "patient-ID scrub must not corrupt synthetic trial IDs"

    embedded = "Diagnosis: NSCLC (Patient: Piotr Test-Wisniewski, ID: SYN-0002)"
    clean = scrub_text(embedded, source)
    assert clean == "Diagnosis: NSCLC"

    evidence = "\n".join([
        "Trial ID: NCT-SYN-0002",
        "NCT id: NCT-SYN-0002",
        "Guideline ID: SG-RE-01",
        "Drug Name: Apalutamide",
        "Gene Name: BRCA1",
    ])
    assert scrub_text(evidence, source) == evidence

    terms = sensitive_terms_from_source(source)
    assert contains_sensitive_term("Diagnosis: NSCLC", terms) is False
    assert contains_sensitive_term("Patient: Piotr Test-Wisniewski", terms) is True


def test_source_identifier_extraction_ignores_evidence_labels() -> None:
    newline_source = "[SYNTHETIC] Patient Name: Alice Example\nDiagnosis: synthetic lymphoma"
    terms = sensitive_terms_from_source(newline_source)
    assert {"Alice Example", "Alice", "Example"} <= terms

    evidence_source = (
        "[SYNTHETIC] Drug Name: Apalutamide. Trial ID: NCT-0002. "
        "Gene Name: BRCA1. Guideline ID: SG-RE-01. Patient ID: SYN-0002."
    )
    terms = sensitive_terms_from_source(evidence_source)
    assert "SYN-0002" in terms
    assert {"Apalutamide", "NCT-0002", "BRCA1", "SG-RE-01"}.isdisjoint(terms)
    assert scrub_text(evidence_source, evidence_source) == (
        "[SYNTHETIC] Drug Name: Apalutamide. Trial ID: NCT-0002. "
        "Gene Name: BRCA1. Guideline ID: SG-RE-01. Patient ID: [REDACTED]"
    )

    odd_spacing = (
        "[SYNTHETIC] Drug  Name: Apalutamide. Trial  ID: NCT-0002. "
        "Trial-ID: NCT-0003. Patient Name: John Doe (MRN: 12345)."
    )
    terms = sensitive_terms_from_source(odd_spacing)
    assert {"John Doe", "John", "Doe", "12345"} <= terms
    assert {"Apalutamide", "NCT-0002", "NCT-0003"}.isdisjoint(terms)

    source = data_tools.get_document_text("E-PII-01")
    terms = sensitive_terms_from_source(source)
    assert {"Malgorzata Synth-Lis", "Malgorzata", "Lis", "90010112345"} <= terms
    scrubbed = scrub_text("Name: Malgorzata Synth-Lis\nTrial ID: NCT-0002", source)
    assert "Malgorzata" not in scrubbed
    assert "NCT-0002" in scrubbed


def test_scrub_obj_recursively_redacts_trace_values() -> None:
    source = data_tools.get_document_text("E-PII-02")
    event = {
        "author": "documentation",
        "type": "tool_call",
        "name": "search_pubmed",
        "args": {
            "query": "DLBCL Czeslaw Synth-Kaczmarek MRN 778899",
            "nested": ["DOB 1958-03-04", {"patient": "Czeslaw Synth-Kaczmarek"}],
        },
    }
    scrubbed = scrub_obj(event, source)
    text = str(scrubbed)
    assert "Czeslaw" not in text
    assert "778899" not in text
    assert "1958-03-04" not in text
    assert scrubbed["name"] == "search_pubmed"  # type: ignore[index]


def test_health_and_cases_are_offline() -> None:
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["location"] == "global"
    assert health.json()["pdq_index_available"] is True
    assert client.get("/healthz").status_code == 200

    cases = client.get("/cases")
    assert cases.status_code == 200
    payload = cases.json()
    ids = {case["case_id"] for case in payload}
    assert {"CASE-001", "CASE-002", "CASE-003", "E-PII-02"} <= ids
    case_003 = next(case for case in payload if case["case_id"] == "CASE-003")
    assert "mri_rectum.txt" in case_003["source_text"]
    assert "mdt_note.txt" in case_003["source_text"]
    assert "cT2 N0" in case_003["source_text"]
    assert "cT3 N1" in case_003["source_text"]
    assert case_003["before"]["label"] == "Unhardened behavior"


def test_run_endpoint_shapes_scrubbed_response(monkeypatch) -> None:
    async def fake_run_case(
        case_id: str,
        max_iterations: int = 4,
        *,
        scrub_output: bool = True,
        include_evidence: bool = True,
    ) -> CaseRun:
        run = CaseRun(case_id=case_id)
        run.events = [
            {"author": "documentation", "type": "text", "text": "Patient Name: Czeslaw Synth-Kaczmarek"},
            {
                "author": "qc",
                "type": "tool_call",
                "name": "search_pubmed",
                "args": {"query": "Czeslaw Synth-Kaczmarek MRN 778899"},
            },
            {"author": "qc", "type": "tool_call", "name": "exit_loop", "args": {}},
        ]
        run.state = {
            "draft": "Patient Name: Czeslaw Synth-Kaczmarek\nMRN: 778899\nDiagnosis: DLBCL",
            "evidence": "NCT-SYN-0002",
            "qc_passed": True,
        }
        return run

    monkeypatch.setattr("service.main.run_case", fake_run_case)
    client = TestClient(app)
    res = client.post("/run", json={"case_id": "E-PII-02", "max_iterations": 4, "include_evidence": False})
    assert res.status_code == 200
    body = res.json()
    combined = body["after"]["draft"] + "\n" + body["after"]["evidence"] + "\n" + str(body["trace"]["events"])
    assert "Czeslaw" not in combined and "778899" not in combined
    assert body["safety"]["post_scrub"] is True
    assert body["safety"]["contains_source_identifier_after_scrub"] is False
    assert body["trace"]["qc_passed"] is True


def test_judge_ui_exposes_evidence_toggle() -> None:
    html = (ROOT / "service" / "static" / "index.html").read_text()
    assert 'id="evidenceToggle"' in html
    assert 'include_evidence: $("evidenceToggle").checked' in html


def test_unknown_case_returns_404() -> None:
    client = TestClient(app)
    res = client.post("/run", json={"case_id": "NOPE"})
    assert res.status_code == 404
