from __future__ import annotations

from app.rag.schemas import Citation, RetrievalResult


def shorten_snippet(text: str, max_chars: int = 180) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def build_citation(result: RetrievalResult, score: float | None = None) -> Citation:
    return Citation(
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        source_doc=result.source_doc,
        page_number=result.page_number,
        section=result.section,
        doc_type=result.doc_type,
        snippet=shorten_snippet(result.snippet),
        score=score if score is not None else (result.fused_score or 0.0),
    )


def format_citation(source_doc: str, page_number: int | None = None, chunk_id: int | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"source_doc": source_doc}
    if page_number is not None:
        payload["page_number"] = page_number
    if chunk_id is not None:
        payload["chunk_id"] = chunk_id
    return payload
