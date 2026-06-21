from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.rag.schemas import IngestionReport


def test_document_upload_endpoint_runs_ingestion(monkeypatch) -> None:
    calls: list[Path] = []

    def fake_ingest_pdf_path(path: Path, db=None):
        calls.append(path)
        return IngestionReport(
            source_doc=path.name,
            chunk_count=2,
            embedding_count=2,
            service_area_count=0,
            branch_hours_count=0,
            source_path=str(path),
            notes=["test"],
        )

    monkeypatch.setattr("app.api.v1.ops.ingest_pdf_path", fake_ingest_pdf_path)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("operator_upload.pdf", b"%PDF-1.4\n% upload smoke\n", "application/pdf")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_doc"] == "operator_upload.pdf"
    assert payload["chunk_count"] == 2
    assert calls and calls[0].name == "operator_upload.pdf"


def test_eval_run_endpoint_persists_summary(monkeypatch) -> None:
    def fake_run_scenario_eval():
        return {
            "eval_name": "operator_ui_eval",
            "total_cases": 2,
            "passed_cases": 2,
            "failed_cases": 0,
            "metrics": {"scenario_pass_rate": 1.0},
            "prompt_versions": {"grounded_answer": "v2"},
        }

    monkeypatch.setattr("app.api.v1.ops.run_scenario_eval", fake_run_scenario_eval)
    monkeypatch.setattr("app.api.v1.ops.write_eval_results", lambda *_: None)
    client = TestClient(create_app())

    response = client.post("/api/v1/evals/run")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["eval_name"] == "operator_ui_eval"
    assert payload["passed_cases"] == 2
    runs = client.get("/api/v1/evals").json()
    assert any(run["eval_name"] == "operator_ui_eval" for run in runs)


def test_tool_registry_can_disable_service_area_tool() -> None:
    client = TestClient(create_app())

    disabled = client.patch("/api/v1/tools/check_service_area", json={"enabled": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False

    tools = client.get("/api/v1/tools").json()
    assert next(tool for tool in tools if tool["tool_name"] == "check_service_area")["enabled"] is False

    blocked = client.post("/api/v1/tools/service-area/check", json={"zip_code": "20147", "service_type": "plumbing"})
    assert blocked.status_code == 400
    assert "disabled" in blocked.json()["detail"].lower()

    reenabled = client.patch("/api/v1/tools/check_service_area", json={"enabled": True})
    assert reenabled.status_code == 200, reenabled.text
    assert reenabled.json()["enabled"] is True
