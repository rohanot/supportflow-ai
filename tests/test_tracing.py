from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from app.db.models import Trace
from app.db.session import make_engine, make_sessionmaker
from tests.conftest import make_client


class FakeTextEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.2 for _ in range(384)] for _ in texts]


def setup_module() -> None:
    import app.rag.embeddings

    app.rag.embeddings.TextEmbedding = FakeTextEmbedding


def test_trace_id_is_in_response_header() -> None:
    client = make_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "X-Trace-Id" in response.headers
    assert len(response.headers["X-Trace-Id"]) >= 16


def test_trace_detail_lists_recent_chat_trace() -> None:
    client = make_client()
    trace_id = f"trace-detail-{uuid4().hex}"
    response = client.post(
        "/api/v1/chat",
        json={"session_id": f"trace-session-{uuid4().hex}", "message": "What is the no-show fee?"},
        headers={"X-Trace-Id": trace_id},
    )
    assert response.status_code == 200, response.text

    detail = client.get(f"/api/v1/traces/{trace_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["trace"]["trace_id"] == trace_id

    session = make_sessionmaker(make_engine())()
    try:
        row = session.execute(select(Trace).where(Trace.trace_id == trace_id)).scalar_one()
        assert row.final_response
    finally:
        session.close()


def test_oversized_trace_id_is_normalized_and_persisted() -> None:
    client = make_client()
    trace_id = "trace-" + "x" * 200
    response = client.post(
        "/api/v1/chat",
        json={"session_id": f"trace-session-{uuid4().hex}", "message": "What is the no-show fee?"},
        headers={"X-Trace-Id": trace_id},
    )
    assert response.status_code == 200, response.text
    normalized = response.headers["X-Trace-Id"]
    assert len(normalized) <= 64
    assert response.json()["trace_id"] == normalized

    detail = client.get(f"/api/v1/traces/{normalized}")
    assert detail.status_code == 200, detail.text
