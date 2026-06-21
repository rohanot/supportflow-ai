from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.graph.clarification import build_canonical_query, plan_clarification
from app.main import create_app


class FakeTextEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.2 for _ in range(384)] for _ in texts]


def setup_module() -> None:
    import app.rag.embeddings

    app.rag.embeddings.TextEmbedding = FakeTextEmbedding


def test_pricing_clarification_asks_one_question() -> None:
    plan = plan_clarification("pricing", {"intent": "pricing"})
    assert plan.missing_fields == ["item_or_service_requested"]
    assert "pricing" in plan.question.lower()


def test_service_area_clarification_requests_zip_and_service() -> None:
    plan = plan_clarification("service_area_check", {"intent": "service_area_check"})
    assert plan.missing_fields == ["zip_code", "service_type"]
    assert "zip code" in plan.question.lower()


def test_build_canonical_query_merges_followup() -> None:
    result = build_canonical_query("Give me the price?", "40-gallon water heater replacement", "pricing")
    assert result == "What is the ballpark price for plumbing 40-gallon water heater replacement?"


def test_ambiguous_pricing_asks_before_retrieval_then_merges_followup() -> None:
    client = TestClient(create_app())
    session_id = f"clarify-pricing-{uuid4().hex}"
    first = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "Give me the price?"},
        headers={"X-Trace-Id": "trace-clarify-pricing-1"},
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["route"] == "ask_clarification"
    assert first_payload["retrieval_used"] is False
    assert "Which service or item" in first_payload["message"]

    second = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "40-gallon water heater replacement."},
        headers={"X-Trace-Id": "trace-clarify-pricing-2"},
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["route"] == "hybrid_rag_answer"
    assert second_payload["canonical_query"] == "What is the ballpark price for plumbing 40-gallon water heater replacement?"
    assert second_payload["retrieval_used"] is True


def test_max_clarification_turns_routes_to_handoff() -> None:
    client = TestClient(create_app())
    session_id = f"clarify-max-turns-{uuid4().hex}"
    for index, message in enumerate(["Book an appointment.", "not sure", "still not sure", "no details"], start=1):
        response = client.post(
            "/api/v1/chat",
            json={"session_id": session_id, "message": message},
            headers={"X-Trace-Id": f"trace-clarify-max-{index}"},
        )
        assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["route"] == "handoff"
    assert payload["handoff_required"] is True
    assert "unable to collect" in payload["handoff_reason"].lower()
