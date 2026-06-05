#!/usr/bin/env python3
"""C6 tests — Cloud Run FastAPI surface + deterministic safety post-scrub (no Vertex calls)."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.pipeline import CaseRun  # noqa: E402
from service import main as service_main  # noqa: E402
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
    assert health.json()["run_auth_required"] is False
    assert health.json()["run_rate_limited"] is True
    assert health.json()["max_agent_iterations"] == 4
    assert health.json()["evidence_enabled"] is True
    assert health.json()["mock_fallback_enabled"] is False
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
    service_main._RUN_CACHE.clear()

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
    assert "search_pubmed" in str(body["trace"]["events"])
    assert "query" in str(body["trace"]["events"])
    assert body["safety"]["post_scrub"] is True
    assert body["safety"]["contains_source_identifier_after_scrub"] is False
    assert body["trace"]["qc_passed"] is True
    assert body["billing"]["cache_hit"] is False


def test_run_endpoint_caches_identical_public_runs(monkeypatch) -> None:
    service_main._RUN_CACHE.clear()
    calls = 0

    async def fake_run_case(
        case_id: str,
        max_iterations: int = 4,
        *,
        scrub_output: bool = True,
        include_evidence: bool = True,
    ) -> CaseRun:
        nonlocal calls
        calls += 1
        run = CaseRun(case_id=case_id)
        run.events = [{"author": "documentation", "type": "text", "text": "Diagnosis: synthetic"}]
        run.state = {"draft": "Diagnosis: synthetic", "evidence": "", "qc_passed": True}
        return run

    monkeypatch.setattr("service.main.run_case", fake_run_case)
    client = TestClient(app)
    first = client.post("/run", json={"case_id": "CASE-001", "max_iterations": 4, "include_evidence": False})
    second = client.post("/run", json={"case_id": "CASE-001", "max_iterations": 4, "include_evidence": False})

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == 1
    assert first.json()["billing"]["cache_hit"] is False
    assert second.json()["billing"]["cache_hit"] is True


def test_auth_status_reports_real_and_mock_modes(monkeypatch) -> None:
    monkeypatch.setenv("RUN_ACCESS_TOKEN", "judge-secret")
    client = TestClient(app)

    missing = client.get("/auth/status")
    assert missing.status_code == 200
    assert missing.json()["run_mode"] == "mock"
    assert missing.json()["token_status"] == "missing"
    assert missing.json()["token_applied"] is False

    invalid = client.get("/auth/status", headers={"Authorization": "Bearer wrong"})
    assert invalid.status_code == 200
    assert invalid.json()["run_mode"] == "mock"
    assert invalid.json()["token_status"] == "invalid"
    assert invalid.json()["token_applied"] is False

    valid = client.get("/auth/status?token=judge-secret")
    assert valid.status_code == 200
    assert valid.json()["run_mode"] == "real"
    assert valid.json()["token_status"] == "valid"
    assert valid.json()["token_applied"] is True
    assert valid.json()["evidence_available"] is True


def test_run_endpoint_returns_mock_without_or_with_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("RUN_ACCESS_TOKEN", "judge-secret")
    client = TestClient(app)

    no_token = client.post(
        "/run",
        json={"case_id": "CASE-003", "max_iterations": 4, "include_evidence": True},
    )
    assert no_token.status_code == 200
    assert no_token.json()["run_mode"] == "mock"
    assert no_token.json()["auth"]["token_status"] == "missing"
    assert no_token.json()["vertex"]["called"] is False
    assert "[MOCK MODE" in no_token.json()["after"]["draft"]
    assert "[DISCREPANCY]" in no_token.json()["after"]["draft"]
    assert no_token.json()["after"]["evidence_requested"] is True
    assert "Mock evidence" in no_token.json()["after"]["evidence"]

    invalid = client.post(
        "/run",
        headers={"Authorization": "Bearer wrong"},
        json={"case_id": "CASE-003", "max_iterations": 4, "include_evidence": False},
    )
    assert invalid.status_code == 200
    assert invalid.json()["run_mode"] == "mock"
    assert invalid.json()["auth"]["token_status"] == "invalid"
    assert invalid.json()["vertex"]["called"] is False


def test_run_endpoint_uses_real_path_when_token_is_valid(monkeypatch) -> None:
    service_main._RUN_CACHE.clear()
    monkeypatch.setenv("RUN_ACCESS_TOKEN", "judge-secret")
    seen: dict[str, object] = {}

    async def fake_run_case(
        case_id: str,
        max_iterations: int = 4,
        *,
        scrub_output: bool = True,
        include_evidence: bool = True,
    ) -> CaseRun:
        seen["case_id"] = case_id
        seen["include_evidence"] = include_evidence
        run = CaseRun(case_id=case_id)
        run.events = [{"author": "documentation", "type": "text", "text": "Diagnosis: synthetic"}]
        run.state = {"draft": "Diagnosis: synthetic", "evidence": "PDQ evidence", "qc_passed": True}
        return run

    monkeypatch.setattr("service.main.run_case", fake_run_case)
    client = TestClient(app)
    res = client.post(
        "/run",
        headers={"Authorization": "Bearer judge-secret"},
        json={"case_id": "CASE-003", "max_iterations": 4, "include_evidence": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["run_mode"] == "real"
    assert body["auth"]["token_status"] == "valid"
    assert body["auth"]["token_applied"] is True
    assert body["vertex"]["called"] is True
    assert seen == {"case_id": "CASE-003", "include_evidence": True}


def test_run_endpoint_rejects_expensive_public_options(monkeypatch) -> None:
    monkeypatch.setenv("RUN_ACCESS_TOKEN", "judge-secret")
    monkeypatch.setenv("MAX_AGENT_ITERATIONS", "3")
    monkeypatch.setenv("ALLOW_EVIDENCE", "false")
    client = TestClient(app)

    mock_evidence = client.post(
        "/run",
        json={"case_id": "CASE-003", "max_iterations": 3, "include_evidence": True},
    )
    assert mock_evidence.status_code == 200
    assert mock_evidence.json()["run_mode"] == "mock"

    too_many_iterations = client.post(
        "/run",
        headers={"Authorization": "Bearer judge-secret"},
        json={"case_id": "CASE-003", "max_iterations": 4, "include_evidence": False},
    )
    assert too_many_iterations.status_code == 400

    evidence = client.post(
        "/run",
        headers={"Authorization": "Bearer judge-secret"},
        json={"case_id": "CASE-003", "max_iterations": 3, "include_evidence": True},
    )
    assert evidence.status_code == 403


def test_run_endpoint_rejects_oversized_request(monkeypatch) -> None:
    monkeypatch.setenv("MAX_REQUEST_BYTES", "10")
    client = TestClient(app)

    res = client.post(
        "/run",
        content='{"case_id":"CASE-003"}',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 413


def test_judge_ui_exposes_evidence_toggle() -> None:
    html = (ROOT / "service" / "static" / "index.html").read_text()
    assert 'id="evidenceToggle"' in html
    assert 'id="tokenInput"' in html
    assert 'id="modeBadge"' in html
    assert 'include_evidence: $("evidenceToggle").checked' in html
    assert "notatnikRunToken" in html
    assert "Authorization" in html
    assert "/auth/status" in html
    assert "Mock mode - paste token for real run" in html
    assert "Real Vertex mode - token accepted" in html
    assert "loadHealth()" in html
    assert "Radioonkolog.pl / Notatnik Medyczny" in html
    assert "https://radioonkolog.pl/polityka/" in html
    assert "https://github.com/kstawiski/notatnik-adk-slice-public" in html
    assert "https://chmura.radioonkolog.pl" not in html
    assert "Synthetic challenge demo only. No real PHI." in html


def test_unknown_case_returns_404() -> None:
    client = TestClient(app)
    res = client.post("/run", json={"case_id": "NOPE"})
    assert res.status_code == 404
