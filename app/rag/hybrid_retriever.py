from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.tracing import get_trace_id
from app.db.models import RetrievalEvent
from app.rag.chunking import normalize_search_text
from app.rag.citation import build_citation, shorten_snippet
from app.rag.embeddings import (
    DEFAULT_EMBEDDING_DIMENSION,
    FastEmbedBackend,
    make_runtime_backend,
)
from app.rag.schemas import (
    Citation,
    DenseResult,
    FusedResult,
    LexicalResult,
    RetrievalDebugInfo,
    RetrievalFilters,
    RetrievalQuery,
    RetrievalResponse,
    RetrievalResult,
)

logger = logging.getLogger(__name__)

DEFAULT_DENSE_TOP_K = 12
DEFAULT_LEXICAL_TOP_K = 12
DEFAULT_FINAL_TOP_K = 5
DEFAULT_RRF_K = 60
VECTOR_SEARCH_MODE = "hnsw_ann"


def _serialize_vector(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def _coerce_vector(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, tuple):
        return [float(item) for item in value]
    if isinstance(value, str):
        raw = value.strip().strip("[]")
        if not raw:
            return []
        return [float(item) for item in raw.split(",")]
    try:
        return [float(item) for item in list(value)]
    except TypeError:
        return []


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    left = left[:length]
    right = right[:length]
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _row_payload(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return dict(row._mapping)


def _snippet_from_row(row: Any) -> str:
    payload = _row_payload(row)
    return shorten_snippet(str(payload.get("chunk_text") or ""))


def _build_conditions(filters: RetrievalFilters, include_eval_data: bool) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if not include_eval_data:
        clauses.append("doc_type NOT IN ('eval_data', 'test_data')")
    if filters.doc_type:
        clauses.append("doc_type = :doc_type")
        params["doc_type"] = filters.doc_type
    if filters.region:
        clauses.append("region = :region")
        params["region"] = filters.region
    if filters.branch:
        clauses.append("branch = :branch")
        params["branch"] = filters.branch
    if filters.service_type:
        clauses.append("(service_type = :service_type OR source_doc ILIKE :service_type_like)")
        params["service_type"] = filters.service_type
        params["service_type_like"] = f"%{filters.service_type}%"
    if filters.policy_type:
        clauses.append("policy_type = :policy_type")
        params["policy_type"] = filters.policy_type
    if filters.source_doc:
        clauses.append("source_doc = :source_doc")
        params["source_doc"] = filters.source_doc
    return (" AND ".join(clauses) if clauses else "TRUE", params)


def _result_from_row(row: Any, *, dense_rank: int | None = None, lexical_rank: int | None = None, dense_score: float | None = None, lexical_score: float | None = None, fused_score: float | None = None) -> RetrievalResult:
    payload = _row_payload(row)
    return RetrievalResult(
        chunk_id=int(payload["id"]),
        document_id=int(payload["document_id"]),
        source_doc=str(payload["source_doc"]),
        page_number=payload.get("page_number"),
        section=payload.get("section"),
        doc_type=payload.get("doc_type"),
        region=payload.get("region"),
        branch=payload.get("branch"),
        service_type=payload.get("service_type"),
        policy_type=payload.get("policy_type"),
        snippet=_snippet_from_row(row),
        dense_rank=dense_rank,
        lexical_rank=lexical_rank,
        dense_score=dense_score,
        lexical_score=lexical_score,
        fused_score=fused_score,
    )


def _as_dense_result(result: RetrievalResult) -> DenseResult:
    return DenseResult.model_validate(result.model_dump())


def _as_lexical_result(result: RetrievalResult) -> LexicalResult:
    return LexicalResult.model_validate(result.model_dump())


def _as_fused_result(result: RetrievalResult) -> FusedResult:
    return FusedResult.model_validate(result.model_dump())


def dense_search(
    db: Session,
    query: str,
    backend: FastEmbedBackend,
    filters: RetrievalFilters,
    top_k: int = DEFAULT_DENSE_TOP_K,
    include_eval_data: bool = False,
) -> list[DenseResult]:
    query_vector = backend.embed([query])[0]
    if len(query_vector) != DEFAULT_EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Expected embedding dimension {DEFAULT_EMBEDDING_DIMENSION}, got {len(query_vector)}."
        )
    where_sql, params = _build_conditions(filters, include_eval_data)
    params.update(
        {
            "query_embedding": _serialize_vector(query_vector),
            "limit": top_k,
        }
    )
    sql = sa.text(
        f"""
        SELECT
            id,
            document_id,
            source_doc,
            page_number,
            section,
            doc_type,
            region,
            branch,
            service_type,
            policy_type,
            chunk_text,
            (embedding <=> CAST(:query_embedding AS vector({DEFAULT_EMBEDDING_DIMENSION}))) AS dense_distance
        FROM chunks
        WHERE {where_sql}
        ORDER BY embedding <=> CAST(:query_embedding AS vector({DEFAULT_EMBEDDING_DIMENSION}))
        LIMIT :limit
        """
    )
    rows = db.execute(sql, params).mappings().all()
    results: list[DenseResult] = []
    for index, row in enumerate(rows, start=1):
        distance = float(row.get("dense_distance") or 0.0)
        similarity = max(0.0, 1.0 - distance)
        results.append(
            _as_dense_result(
                _result_from_row(
                    row,
                    dense_rank=index,
                    dense_score=similarity,
                )
            )
        )
    return results


def dense_search_exact(
    db: Session,
    query: str,
    backend: FastEmbedBackend,
    filters: RetrievalFilters,
    top_k: int = DEFAULT_DENSE_TOP_K,
    include_eval_data: bool = False,
) -> list[DenseResult]:
    query_vector = backend.embed([query])[0]
    if len(query_vector) != DEFAULT_EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Expected embedding dimension {DEFAULT_EMBEDDING_DIMENSION}, got {len(query_vector)}."
        )
    where_sql, params = _build_conditions(filters, include_eval_data)
    sql = sa.text(
        f"""
        SELECT
            id,
            document_id,
            source_doc,
            page_number,
            section,
            doc_type,
            region,
            branch,
            service_type,
            policy_type,
            chunk_text,
            embedding
        FROM chunks
        WHERE {where_sql}
        """
    )
    rows = db.execute(sql, params).mappings().all()
    scored_rows: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        candidate_vector = _coerce_vector(row.get("embedding"))
        similarity = _cosine_similarity(query_vector, candidate_vector)
        scored_rows.append((similarity, row))
    scored_rows.sort(key=lambda item: (-item[0], int(item[1]["id"])))
    results: list[DenseResult] = []
    for index, (similarity, row) in enumerate(scored_rows[:top_k], start=1):
        results.append(
            _as_dense_result(
                _result_from_row(
                    row,
                    dense_rank=index,
                    dense_score=max(0.0, similarity),
                )
            )
        )
    return results


def lexical_search(
    db: Session,
    query: str,
    filters: RetrievalFilters,
    top_k: int = DEFAULT_LEXICAL_TOP_K,
    include_eval_data: bool = False,
) -> list[LexicalResult]:
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return []
    where_sql, params = _build_conditions(filters, include_eval_data)

    def _run_lexical(tsquery_expression: str, param_name: str) -> list[dict[str, Any]]:
        query_params = dict(params)
        query_params.update({param_name: tsquery_expression, "limit": top_k})
        sql = sa.text(
            f"""
            WITH query_ts AS (
                SELECT to_tsquery('english', :{param_name}) AS query
            )
            SELECT
                c.id,
                c.document_id,
                c.source_doc,
                c.page_number,
                c.section,
                c.doc_type,
                c.region,
                c.branch,
                c.service_type,
                c.policy_type,
                c.chunk_text,
                ts_rank_cd(COALESCE(c.search_vector, to_tsvector('english', c.chunk_text)), query_ts.query) AS lexical_score
            FROM chunks AS c, query_ts
            WHERE COALESCE(c.search_vector, to_tsvector('english', c.chunk_text)) @@ query_ts.query
              AND {where_sql}
            ORDER BY lexical_score DESC, c.id ASC
            LIMIT :limit
            """
        )
        return db.execute(sql, query_params).mappings().all()

    strict_query = " & ".join(normalized_query.split())
    rows = _run_lexical(strict_query, "strict_query")
    if not rows:
        loose_tokens = [token for token in normalized_query.split() if token]
        loose_query = " | ".join(loose_tokens)
        if loose_query and loose_query != strict_query:
            rows = _run_lexical(loose_query, "loose_query")

    results: list[LexicalResult] = []
    for index, row in enumerate(rows, start=1):
        score = float(row.get("lexical_score") or 0.0)
        results.append(
            _as_lexical_result(
                _result_from_row(
                    row,
                    lexical_rank=index,
                    lexical_score=score,
                )
            )
        )
    return results


def fuse_results(
    dense_results: list[DenseResult],
    lexical_results: list[LexicalResult],
    final_top_k: int = DEFAULT_FINAL_TOP_K,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[FusedResult]:
    fused: dict[int, dict[str, Any]] = {}

    for result in dense_results:
        fused.setdefault(
            result.chunk_id,
            result.model_dump(),
        )
        fused[result.chunk_id]["dense_rank"] = result.dense_rank
        fused[result.chunk_id]["dense_score"] = result.dense_score

    for result in lexical_results:
        current = fused.setdefault(result.chunk_id, result.model_dump())
        current["lexical_rank"] = result.lexical_rank
        current["lexical_score"] = result.lexical_score

    fused_results: list[FusedResult] = []
    for payload in fused.values():
        dense_rank = payload.get("dense_rank")
        lexical_rank = payload.get("lexical_rank")
        fused_score = 0.0
        if dense_rank:
            fused_score += 1.0 / (rrf_k + int(dense_rank))
        if lexical_rank:
            fused_score += 1.0 / (rrf_k + int(lexical_rank))
        payload["fused_score"] = fused_score
        fused_results.append(FusedResult.model_validate(payload))

    fused_results.sort(
        key=lambda result: (
            -(result.fused_score or 0.0),
            result.dense_rank if result.dense_rank is not None else 10_000,
            result.lexical_rank if result.lexical_rank is not None else 10_000,
            result.chunk_id,
        )
    )
    return fused_results[:final_top_k]


def build_confidence(
    *,
    fused_results: list[FusedResult],
    dense_results: list[DenseResult],
    lexical_results: list[LexicalResult],
    filters: RetrievalFilters,
    citations: list[Citation],
    final_top_k: int,
    rrf_k: int = DEFAULT_RRF_K,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if fused_results:
        max_rrf = 2.0 / (rrf_k + 1)
        strength = min(1.0, (fused_results[0].fused_score or 0.0) / max_rrf) if max_rrf else 0.0
    else:
        strength = 0.0
    count_factor = min(1.0, len(fused_results) / max(final_top_k, 1))
    if filters.doc_type:
        doc_type_match = 1.0 if any(result.doc_type == filters.doc_type for result in fused_results) else 0.0
    else:
        doc_type_match = 1.0 if fused_results else 0.0
    citation_factor = 1.0 if citations else 0.0
    agreement = 1.0 if any(result.dense_rank and result.lexical_rank for result in fused_results) else (
        0.5 if dense_results or lexical_results else 0.0
    )

    if fused_results:
        reasons.append(f"fused_score_strength={strength:.2f}")
        reasons.append(f"results_returned={len(fused_results)}")
    if filters.doc_type:
        reasons.append(f"doc_type_filter={filters.doc_type}")
        reasons.append("doc_type_match=yes" if doc_type_match > 0 else "doc_type_match=no")
    if citations:
        reasons.append("citations_available=yes")
    if any(result.dense_rank and result.lexical_rank for result in fused_results):
        reasons.append("dense_and_lexical_agree=yes")

    confidence = (
        0.35 * strength
        + 0.20 * count_factor
        + 0.15 * doc_type_match
        + 0.15 * citation_factor
        + 0.15 * agreement
    )
    confidence = max(0.0, min(1.0, round(confidence, 4)))
    return confidence, reasons


def _build_selected_context(fused_results: list[FusedResult]) -> str | None:
    if not fused_results:
        return None
    return "\n".join(result.snippet for result in fused_results[:3] if result.snippet)


def _build_debug_info(
    *,
    trace_id: str,
    backend: FastEmbedBackend,
    query: RetrievalQuery,
    latency_ms: int,
    dense_results: list[DenseResult],
    lexical_results: list[LexicalResult],
    fused_results: list[FusedResult],
    confidence_reasons: list[str],
    include_eval_data: bool,
) -> RetrievalDebugInfo:
    return RetrievalDebugInfo(
        trace_id=trace_id,
        embedding_backend=getattr(backend, "embedding_backend", "fastembed"),
        embedding_model=getattr(backend, "embedding_model", "unknown"),
        embedding_dimension=getattr(backend, "embedding_dimension", DEFAULT_EMBEDDING_DIMENSION),
        vector_search_mode=VECTOR_SEARCH_MODE,
        eval_data_excluded=not include_eval_data,
        dense_top_k=DEFAULT_DENSE_TOP_K,
        lexical_top_k=DEFAULT_LEXICAL_TOP_K,
        final_top_k=query.top_k,
        latency_ms=latency_ms,
        dense_query=query.canonical_query or query.query,
        normalized_query=normalize_search_text(query.canonical_query or query.query),
        filters=query.filters.model_dump(exclude_none=True),
        dense_candidate_count=len(dense_results),
        lexical_candidate_count=len(lexical_results),
        fused_candidate_count=len(fused_results),
        selected_chunk_ids=[result.chunk_id for result in fused_results],
        selected_source_docs=sorted({result.source_doc for result in fused_results}),
        confidence_reasons=confidence_reasons,
    )


def persist_retrieval_event(
    db: Session | None,
    *,
    trace_id: str,
    query: RetrievalQuery,
    dense_results: list[DenseResult],
    lexical_results: list[LexicalResult],
    fused_results: list[FusedResult],
    citations: list[Citation],
    confidence: float,
    confidence_reasons: list[str],
    backend: FastEmbedBackend,
    latency_ms: int,
    include_eval_data: bool,
) -> None:
    if db is None:
        return
    selected_context = _build_selected_context(fused_results)
    db.add(
        RetrievalEvent(
            trace_id=trace_id,
            session_id=None,
            query=query.query,
            canonical_query=query.canonical_query,
            filters_json={
                "filters": query.filters.model_dump(exclude_none=True),
                "dense_top_k": DEFAULT_DENSE_TOP_K,
                "lexical_top_k": DEFAULT_LEXICAL_TOP_K,
                "final_top_k": query.top_k,
                "embedding_backend": getattr(backend, "embedding_backend", None),
                "embedding_model": getattr(backend, "embedding_model", None),
                "embedding_dimension": getattr(backend, "embedding_dimension", None),
                "vector_search_mode": VECTOR_SEARCH_MODE,
                "eval_data_excluded": not include_eval_data,
                "latency_ms": latency_ms,
                "confidence_reasons": confidence_reasons,
            },
            dense_top_k=DEFAULT_DENSE_TOP_K,
            lexical_top_k=DEFAULT_LEXICAL_TOP_K,
            fused_top_k=query.top_k,
            dense_results_json=[result.model_dump(mode="json") for result in dense_results],
            lexical_results_json=[result.model_dump(mode="json") for result in lexical_results],
            fused_results_json=[result.model_dump(mode="json") for result in fused_results],
            selected_context=selected_context,
            citation_ids_json=[citation.chunk_id for citation in citations],
            retrieval_confidence=confidence,
        )
    )
    db.commit()


def run_hybrid_retrieval(
    db: Session,
    request: RetrievalQuery,
    *,
    backend: FastEmbedBackend | None = None,
    trace_id: str | None = None,
    include_eval_data: bool = False,
) -> RetrievalResponse:
    resolved_trace_id = trace_id or get_trace_id()
    resolved_backend = backend or make_runtime_backend()
    started_at = time.perf_counter()
    search_text = request.canonical_query or request.query

    dense_results = dense_search(
        db,
        search_text,
        resolved_backend,
        request.filters,
        top_k=DEFAULT_DENSE_TOP_K,
        include_eval_data=include_eval_data,
    )
    lexical_results = lexical_search(
        db,
        search_text,
        request.filters,
        top_k=DEFAULT_LEXICAL_TOP_K,
        include_eval_data=include_eval_data,
    )
    fused_results = fuse_results(
        dense_results,
        lexical_results,
        final_top_k=request.top_k or DEFAULT_FINAL_TOP_K,
    )
    citations = [build_citation(result, score=result.fused_score or 0.0) for result in fused_results]
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    confidence, confidence_reasons = build_confidence(
        fused_results=fused_results,
        dense_results=dense_results,
        lexical_results=lexical_results,
        filters=request.filters,
        citations=citations,
        final_top_k=request.top_k or DEFAULT_FINAL_TOP_K,
    )
    debug = _build_debug_info(
        trace_id=resolved_trace_id,
        backend=resolved_backend,
        query=request,
        latency_ms=latency_ms,
        dense_results=dense_results,
        lexical_results=lexical_results,
        fused_results=fused_results,
        confidence_reasons=confidence_reasons,
        include_eval_data=include_eval_data,
    )
    persist_retrieval_event(
        db,
        trace_id=resolved_trace_id,
        query=request,
        dense_results=dense_results,
        lexical_results=lexical_results,
        fused_results=fused_results,
        citations=citations,
        confidence=confidence,
        confidence_reasons=confidence_reasons,
        backend=resolved_backend,
        latency_ms=latency_ms,
        include_eval_data=include_eval_data,
    )
    logger.info(
        "retrieval completed",
        extra={
            "trace_id": resolved_trace_id,
            "embedding_backend": getattr(resolved_backend, "embedding_backend", None),
            "embedding_model": getattr(resolved_backend, "embedding_model", None),
            "embedding_dimension": getattr(resolved_backend, "embedding_dimension", None),
            "fallback_allowed": getattr(resolved_backend, "fallback_allowed", False),
        },
    )
    return RetrievalResponse(
        trace_id=resolved_trace_id,
        query=request.query,
        canonical_query=request.canonical_query,
        applied_filters=request.filters.model_dump(exclude_none=True),
        dense_results=dense_results,
        lexical_results=lexical_results,
        fused_results=fused_results,
        citations=citations,
        confidence=confidence,
        confidence_reasons=confidence_reasons,
        debug=debug if request.include_debug else RetrievalDebugInfo(
            trace_id=resolved_trace_id,
            vector_search_mode=VECTOR_SEARCH_MODE,
            eval_data_excluded=not include_eval_data,
        ),
    )
