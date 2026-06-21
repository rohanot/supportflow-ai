from __future__ import annotations

from typing import Iterable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk
from app.db.session import make_engine, make_sessionmaker
from app.main import create_app
from app.rag.embeddings import FastEmbedBackend
from app.rag.hybrid_retriever import (
    VECTOR_SEARCH_MODE,
    dense_search,
    dense_search_exact,
    fuse_results,
    lexical_search,
    run_hybrid_retrieval,
)
from app.rag.schemas import RetrievalFilters, RetrievalQuery


def _chunk_vector(session: Session, source_doc: str, fragment: str) -> list[float]:
    chunk = (
        session.execute(
            select(Chunk)
            .where(Chunk.source_doc == source_doc, Chunk.chunk_text.ilike(f"%{fragment}%"))
            .order_by(Chunk.id)
        )
        .scalars()
        .first()
    )
    assert chunk is not None, f"Missing chunk for {source_doc!r} containing {fragment!r}"
    embedding = chunk.embedding
    if embedding is None:
        return []
    if isinstance(embedding, str):
        raw = embedding.strip().strip("[]")
        if not raw:
            return []
        return [float(value) for value in raw.split(",") if value.strip()]
    return [float(value) for value in embedding]


class QueryAlignedBackend:
    embedding_backend = "fastembed"
    embedding_model = "BAAI/bge-small-en-v1.5"
    embedding_dimension = 384
    fallback_allowed = False

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def _vector_for(self, text: str) -> list[float]:
        lowered = text.lower()
        rules: list[tuple[tuple[str, ...], str]] = [
            (("water heater", "price"), "water_heater_pricing"),
            (("herndon", "saturday", "hours"), "herndon_hours"),
            (("no-show", "fee"), "no_show_fee"),
            (("emergency", "line"), "emergency_line"),
            (("panel upgrade", "200a"), "panel_upgrade"),
            (("$75", "no-show"), "eval_no_show"),
        ]
        for tokens, vector_name in rules:
            if all(token in lowered for token in tokens):
                return self.vectors[vector_name]
        return self.vectors["water_heater_pricing"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for(text) for text in texts]


def _make_session() -> Session:
    engine = make_engine()
    return make_sessionmaker(engine)()


def _make_backend(session: Session) -> QueryAlignedBackend:
    vectors = {
        "water_heater_pricing": _chunk_vector(session, "04_plumbing_pricing.pdf", "Water heater replacement"),
        "herndon_hours": _chunk_vector(session, "08_branch_hours.pdf", "Saturday 8:00 am"),
        "no_show_fee": _chunk_vector(session, "07_cancellation_policy.pdf", "Cancellation & Rescheduling Policy"),
        "emergency_line": _chunk_vector(session, "11_faq_emergencies.pdf", "FAQ — Emergencies"),
        "panel_upgrade": _chunk_vector(session, "05_electrical_pricing.pdf", "Full panel upgrade"),
        "eval_no_show": _chunk_vector(session, "13_customer_messages.pdf", "no-show"),
    }
    return QueryAlignedBackend(vectors)


def _assert_expected_source_doc(results: Iterable[dict[str, object]], expected_source_docs: set[str]) -> None:
    source_docs = {str(result["source_doc"]) for result in results}
    assert source_docs & expected_source_docs, f"Expected one of {expected_source_docs}, got {source_docs}"


def test_fastembed_backend_prefers_runtime_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTextEmbedding:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1 for _ in range(384)] for _ in texts]

    monkeypatch.setattr("app.rag.embeddings.TextEmbedding", FakeTextEmbedding, raising=False)
    backend = FastEmbedBackend()

    assert backend.embedding_backend == "fastembed"
    assert backend.fallback_allowed is False
    assert len(backend.embed(["hello"])[0]) == 384


def test_dense_and_lexical_retrieval_return_results() -> None:
    session = _make_session()
    try:
        backend = _make_backend(session)
        filters = RetrievalFilters(doc_type="pricing", service_type="plumbing")

        dense_results = dense_search(session, "40 gallon water heater replacement price", backend, filters)
        lexical_results = lexical_search(session, "40 gallon water heater replacement price", filters)

        assert dense_results
        assert lexical_results
        assert dense_results[0].source_doc == "04_plumbing_pricing.pdf"
        assert lexical_results[0].source_doc == "04_plumbing_pricing.pdf"
    finally:
        session.close()


def test_rrf_fusion_is_stable_and_returns_expected_docs() -> None:
    session = _make_session()
    try:
        backend = _make_backend(session)
        filters = RetrievalFilters(doc_type="pricing", service_type="plumbing")

        dense_results = dense_search(session, "40 gallon water heater replacement price", backend, filters)
        lexical_results = lexical_search(session, "40 gallon water heater replacement price", filters)
        fused_first = fuse_results(dense_results, lexical_results)
        fused_second = fuse_results(dense_results, lexical_results)

        assert fused_first
        assert [result.chunk_id for result in fused_first] == [result.chunk_id for result in fused_second]
        assert fused_first[0].source_doc == "04_plumbing_pricing.pdf"
        assert fused_first[0].fused_score is not None
    finally:
        session.close()


def test_metadata_filtering_works() -> None:
    session = _make_session()
    try:
        backend = _make_backend(session)
        response = run_hybrid_retrieval(
            session,
            RetrievalQuery(
                query="panel upgrade 100A to 200A",
                filters=RetrievalFilters(doc_type="pricing", service_type="electrical"),
                top_k=5,
                include_debug=True,
            ),
            backend=backend,
        )

        assert response.fused_results
        assert all(result.doc_type == "pricing" for result in response.fused_results)
        assert response.fused_results[0].source_doc == "05_electrical_pricing.pdf"
        assert response.debug.vector_search_mode == VECTOR_SEARCH_MODE
    finally:
        session.close()


def test_eval_documents_are_excluded_from_default_retrieval() -> None:
    session = _make_session()
    try:
        backend = _make_backend(session)
        response = run_hybrid_retrieval(
            session,
            RetrievalQuery(
                query="I got charged $75 for a no-show but I called to cancel",
                top_k=5,
                include_debug=True,
            ),
            backend=backend,
        )

        assert response.fused_results
        assert "13_customer_messages.pdf" not in {result.source_doc for result in response.fused_results}
        assert "13_customer_messages.pdf" not in {citation.source_doc for citation in response.citations}
        assert response.debug.eval_data_excluded is True
    finally:
        session.close()


def test_citations_and_confidence_are_deterministic() -> None:
    session = _make_session()
    try:
        backend = _make_backend(session)
        request = RetrievalQuery(
            query="Herndon Saturday hours",
            filters=RetrievalFilters(doc_type="branch_hours"),
            top_k=5,
            include_debug=True,
        )

        first = run_hybrid_retrieval(session, request, backend=backend)
        second = run_hybrid_retrieval(session, request, backend=backend)

        assert first.confidence == second.confidence
        assert first.confidence_reasons == second.confidence_reasons
        assert first.citations
        assert first.citations[0].source_doc == "08_branch_hours.pdf"
        assert first.citations[0].score == first.fused_results[0].fused_score
    finally:
        session.close()


def test_exact_vector_baseline_exists_for_eval_debug() -> None:
    session = _make_session()
    try:
        backend = _make_backend(session)
        exact_results = dense_search_exact(
            session,
            "40 gallon water heater replacement price",
            backend,
            RetrievalFilters(doc_type="pricing", service_type="plumbing"),
            top_k=3,
        )

        assert exact_results
        assert exact_results[0].source_doc == "04_plumbing_pricing.pdf"
    finally:
        session.close()


def test_hnsw_ann_is_default_dense_retrieval_path() -> None:
    session = _make_session()
    try:
        backend = _make_backend(session)
        response = run_hybrid_retrieval(
            session,
            RetrievalQuery(
                query="panel upgrade 100A to 200A",
                filters=RetrievalFilters(doc_type="pricing", service_type="electrical"),
                top_k=5,
                include_debug=True,
            ),
            backend=backend,
        )

        assert response.debug.vector_search_mode == VECTOR_SEARCH_MODE
    finally:
        session.close()


def test_retrieval_endpoint_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    backend = _make_backend(session)
    monkeypatch.setattr("app.rag.hybrid_retriever.make_runtime_backend", lambda: backend)
    client = TestClient(create_app())
    try:
        response = client.post(
            "/api/v1/retrieval/test",
            json={
                "query": "40 gallon water heater replacement price",
                "filters": {"doc_type": "pricing", "service_type": "plumbing"},
                "top_k": 5,
                "include_debug": True,
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["trace_id"]
        assert payload["fused_results"]
        assert payload["citations"]
        assert payload["debug"]["vector_search_mode"] == VECTOR_SEARCH_MODE
    finally:
        session.close()
