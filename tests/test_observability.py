from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import ClarificationEvent, GraphNodeEvent, PromptEvent, RetrievalEvent, ToolInvocation, Trace
from app.db.session import make_engine, make_sessionmaker
from app.main import create_app
from app.prompts.manager import PromptManager


class FakeTextEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.2 for _ in range(384)] for _ in texts]


def setup_module() -> None:
    import app.rag.embeddings

    app.rag.embeddings.TextEmbedding = FakeTextEmbedding


def _client() -> TestClient:
    return TestClient(create_app())


def _session():
    return make_sessionmaker(make_engine())()


def test_trace_id_generated_for_chat_request() -> None:
    client = _client()
    response = client.post(
        "/api/v1/chat",
        json={"session_id": f"obs-chat-{uuid4().hex}", "message": "What is the no-show fee?"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["X-Trace-Id"]
    assert response.json()["trace_id"] == response.headers["X-Trace-Id"]


def test_trace_detail_and_subendpoints_work() -> None:
    client = _client()
    trace_id = f"obs-trace-{uuid4().hex}"
    chat = client.post(
        "/api/v1/chat",
        json={"session_id": f"obs-session-{uuid4().hex}", "message": "Herndon Saturday hours"},
        headers={"X-Trace-Id": trace_id},
    )
    assert chat.status_code == 200, chat.text

    for path in [
        f"/api/v1/traces/{trace_id}",
        f"/api/v1/traces/{trace_id}/graph",
        f"/api/v1/traces/{trace_id}/retrieval",
        f"/api/v1/traces/{trace_id}/prompts",
        f"/api/v1/traces/{trace_id}/tools",
        f"/api/v1/traces/{trace_id}/clarification",
    ]:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)


def test_retrieval_clarification_graph_and_tool_events_are_persisted() -> None:
    client = _client()
    session_id = f"obs-session-{uuid4().hex}"
    pricing_trace = f"obs-pricing-{uuid4().hex}"
    clarify = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "Give me the price?"},
        headers={"X-Trace-Id": pricing_trace},
    )
    assert clarify.status_code == 200, clarify.text
    assert clarify.json()["route"] == "ask_clarification"

    retrieval = client.post(
        "/api/v1/retrieval/test",
        json={"query": "What is the no-show fee?", "top_k": 5, "include_debug": True},
        headers={"X-Trace-Id": f"obs-retrieval-{uuid4().hex}"},
    )
    assert retrieval.status_code == 200, retrieval.text

    booking_trace = f"obs-booking-{uuid4().hex}"
    blocked = client.post(
        "/mock/bookings",
        json={
            "customer_id": f"cust-{uuid4().hex[:8]}",
            "service_type": "plumbing",
            "job_type": "water heater replacement",
            "zip_code": "20147",
            "preferred_date": "2026-07-01",
            "preferred_window": "morning",
            "channel": "chat",
        },
        headers={"X-Trace-Id": booking_trace},
    )
    assert blocked.status_code == 200, blocked.text

    session = _session()
    try:
        assert session.execute(select(ClarificationEvent).where(ClarificationEvent.trace_id == pricing_trace)).scalars().all()
        assert session.execute(select(GraphNodeEvent).where(GraphNodeEvent.trace_id == pricing_trace)).scalars().all()
        assert session.execute(select(RetrievalEvent).where(RetrievalEvent.trace_id == retrieval.json()["trace_id"])).scalars().all()
        assert session.execute(select(ToolInvocation).where(ToolInvocation.trace_id == booking_trace)).scalars().all()
    finally:
        session.close()


def test_sensitive_fields_are_redacted_in_trace_detail() -> None:
    client = _client()
    trace_id = f"obs-redact-{uuid4().hex}"
    client.post(
        "/api/v1/chat",
        json={"session_id": f"obs-redact-session-{uuid4().hex}", "message": "My SSN is 123-45-6789 and zip 20147"},
        headers={"X-Trace-Id": trace_id},
    )

    response = client.get(f"/api/v1/traces/{trace_id}")
    assert response.status_code == 200, response.text
    text = response.text
    assert "123-45-6789" not in text
    assert "[SSN]" in text


def test_local_tracing_works_without_langfuse() -> None:
    client = _client()
    response = client.get("/api/health")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_prompt_render_event_is_persisted_when_trace_context_is_supplied() -> None:
    session = _session()
    try:
        manager = PromptManager()
        trace_id = f"obs-prompt-{uuid4().hex}"
        rendered = manager.render_prompt(
            "ask_clarification",
            db=session,
            trace_id=trace_id,
            intent="pricing",
            missing_fields=["item_or_service_requested"],
        )
        assert rendered.prompt_name == "ask_clarification"
        session.commit()
        rows = session.execute(select(PromptEvent).where(PromptEvent.trace_id == trace_id)).scalars().all()
        assert rows
    finally:
        session.close()
