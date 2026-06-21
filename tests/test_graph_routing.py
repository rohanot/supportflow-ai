from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Chunk, ConversationState, GraphNodeEvent
from app.db.session import make_engine, make_sessionmaker
from app.graph.state import ConversationStateData, save_conversation_state
from app.graph.nodes import _build_retrieval_context, _polish_grounded_answer
from app.rag.schemas import Citation
from app.main import create_app


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


def test_emergency_routes_to_handoff_without_retrieval() -> None:
    client = _client()
    session_id = f"graph-emergency-{uuid4().hex}"
    response = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "Water is pouring under my sink"},
        headers={"X-Trace-Id": "trace-graph-emergency"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["route"] == "handoff"
    assert payload["handoff_required"] is True
    assert "emergency" in payload["handoff_reason"].lower()
    assert payload["retrieval_used"] is False


def test_faq_routes_to_hybrid_retrieval() -> None:
    client = _client()
    session_id = f"graph-faq-{uuid4().hex}"
    response = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "What is the no-show fee?"},
        headers={"X-Trace-Id": "trace-graph-faq"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["route"] == "hybrid_rag_answer"
    assert payload["retrieval_used"] is True
    assert payload["citations"]
    assert payload["trace_id"] == "trace-graph-faq"


def test_completed_state_does_not_contaminate_new_question() -> None:
    session_id = f"graph-state-reset-{uuid4().hex}"
    session = _session()
    try:
        save_conversation_state(
            session,
            ConversationStateData(
                session_id=session_id,
                state_json={
                    "session_id": session_id,
                    "trace_id": "old-trace",
                    "user_message": "What does a water heater replacement cost?",
                    "route": "hybrid_rag_answer",
                    "intent": "pricing",
                    "canonical_query": "water heater replacement cost",
                    "service_type": "plumbing",
                    "item_or_service_requested": "water heater replacement",
                    "clarification_question": None,
                    "pending_intent": None,
                },
                missing_fields_json=[],
                awaiting_user_input=False,
                awaiting_confirmation=False,
            ),
        )
        session.commit()
    finally:
        session.close()

    client = _client()
    second = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "What is the no-show fee?"},
        headers={"X-Trace-Id": f"trace-state-reset-2-{uuid4().hex}"},
    )

    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["route"] == "hybrid_rag_answer"
    assert payload["canonical_query"] != "water heater replacement cost"
    assert any(citation["source_doc"] == "07_cancellation_policy.pdf" for citation in payload["citations"])


def test_grounded_answer_context_uses_full_chunk_text() -> None:
    session = _session()
    try:
        chunk = (
            session.execute(
                select(Chunk).where(
                    Chunk.source_doc == "07_cancellation_policy.pdf",
                    Chunk.chunk_text.ilike("%$75 no-show fee%"),
                )
            )
            .scalars()
            .first()
        )
        assert chunk is not None
        context = _build_retrieval_context(session, [chunk.id])
        assert "$75 no-show fee" in context
    finally:
        session.close()


def test_bare_numeric_grounded_answer_is_polished_with_source() -> None:
    citation = Citation(
        chunk_id=1,
        document_id=1,
        source_doc="07_cancellation_policy.pdf",
        page_number=None,
        section="policy",
        doc_type="policy",
        snippet="$75 no-show fee",
        score=0.9,
    )

    answer = _polish_grounded_answer("$75", "no-show fee", [citation])

    assert answer == "The no-show fee is $75, according to 07_cancellation_policy.pdf."


def test_vague_pricing_answer_is_polished_with_price_range() -> None:
    citation = Citation(
        chunk_id=1,
        document_id=1,
        source_doc="04_plumbing_pricing.pdf",
        page_number=None,
        section="pricing",
        doc_type="pricing",
        snippet="Water heater replacement (40 gal)\n$950 - $1,400\nTankless: quote required",
        score=0.9,
    )

    answer = _polish_grounded_answer(
        "The cost is available in the pricing document.",
        "water heater replacement cost",
        [citation],
    )

    assert answer == "The water heater replacement cost is $950 - $1,400, according to 04_plumbing_pricing.pdf."


def test_service_area_followup_routes_to_structured_lookup() -> None:
    client = _client()
    session_id = f"graph-service-area-{uuid4().hex}"
    first = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "Do you service my area?"},
        headers={"X-Trace-Id": "trace-graph-service-area-1"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["route"] == "ask_clarification"

    second = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "20147 plumbing"},
        headers={"X-Trace-Id": "trace-graph-service-area-2"},
    )

    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["route"] == "service_area_lookup"
    assert payload["canonical_query"] == "Check service-area eligibility for plumbing in ZIP 20147."
    assert payload["service_area"]["eligible"] is True
    assert payload["service_area"]["service_status"] == "sub-contracted"


def test_graph_node_trace_is_persisted() -> None:
    client = _client()
    session_id = f"graph-trace-{uuid4().hex}"
    response = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "What are Herndon Saturday hours?"},
        headers={"X-Trace-Id": "trace-graph-node-persisted"},
    )
    assert response.status_code == 200, response.text

    session = _session()
    try:
        events = (
            session.execute(
                select(GraphNodeEvent)
                .where(GraphNodeEvent.trace_id == "trace-graph-node-persisted")
                .order_by(GraphNodeEvent.id)
            )
            .scalars()
            .all()
        )
        assert events
        assert {event.node_name for event in events} >= {"classify_intent", "route_intent", "final_response"}
    finally:
        session.close()


def test_conversation_state_persists_across_turns() -> None:
    client = _client()
    session_id = f"graph-state-persists-{uuid4().hex}"
    client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "Give me the price?"},
        headers={"X-Trace-Id": "trace-state-1"},
    )

    session = _session()
    try:
        row = session.execute(select(ConversationState).where(ConversationState.session_id == session_id)).scalar_one()
        assert row.pending_intent == "pricing"
        assert row.awaiting_user_input is True
        assert "item_or_service_requested" in row.missing_fields_json
    finally:
        session.close()
