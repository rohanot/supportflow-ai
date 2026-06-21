from __future__ import annotations

from pathlib import Path
from typing import Iterable

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import BranchHours, Chunk, Document, ServiceArea
from app.rag.chunking import (
    chunk_document_text,
    infer_document_profile,
    normalize_search_text,
)
from app.rag.embeddings import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    FastEmbedBackend,
    build_chunk_embedding_metadata,
)
from app.rag.schemas import BranchHoursRecord, ChunkRecord, IngestionReport, ServiceAreaRecord

try:  # pragma: no cover - optional in local shell, present in Docker
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

class EmbeddingBackend:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


def extract_pdf_text(path: Path) -> str:
    if PdfReader is None:
        return path.read_text(encoding="utf-8", errors="ignore")
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def build_hnsw_index_ddl(index_name: str = "ix_chunks_embedding_hnsw") -> str:
    return f"CREATE INDEX IF NOT EXISTS {index_name} ON chunks USING hnsw (embedding vector_cosine_ops)"


def build_search_vector_text(text: str) -> str:
    return normalize_search_text(text)


def ingest_pdf_path(
    path: Path,
    db: Session | None = None,
    embedder: EmbeddingBackend | None = None,
) -> IngestionReport:
    settings = get_settings()
    embedder = embedder or FastEmbedBackend(allow_fallback_embeddings=settings.allow_fallback_embeddings)
    profile = infer_document_profile(path)
    text = extract_pdf_text(path)
    chunks, service_area_records, branch_hours_records = chunk_document_text(text, profile.source_doc, profile.doc_type)
    chunk_texts = [chunk.chunk_text for chunk in chunks]
    embeddings = embedder.embed(chunk_texts) if chunk_texts else []
    for chunk, embedding in zip(chunks, embeddings, strict=False):
        chunk.embedding = embedding
        chunk.search_vector = chunk.search_vector or build_search_vector_text(chunk.chunk_text)
        chunk.metadata.update(
            build_chunk_embedding_metadata(
                embedding_backend=getattr(embedder, "embedding_backend", "fastembed"),
                embedding_model=getattr(embedder, "embedding_model", DEFAULT_EMBEDDING_MODEL),
                embedding_dimension=getattr(embedder, "embedding_dimension", DEFAULT_EMBEDDING_DIMENSION),
                fallback_allowed=getattr(embedder, "fallback_allowed", False),
            )
        )
    if db is not None:
        delete_existing_source_rows(db, profile.source_doc)
        document_id = upsert_document(db, profile, text)
        persist_chunks(db, document_id, chunks)
        persist_service_areas(db, service_area_records, text)
        persist_branch_hours(db, branch_hours_records, text)
        db.commit()
        rebuild_chunk_indexes(db)
    return IngestionReport(
        source_doc=profile.source_doc,
        chunk_count=len(chunks),
        service_area_count=len(service_area_records),
        branch_hours_count=len(branch_hours_records),
        embedding_count=len(embeddings),
        source_path=str(path),
        notes=["hnsw_ddl:" + build_hnsw_index_ddl()],
    )


def upsert_document(db: Session, profile, text: str) -> int:
    existing = db.execute(select(Document).where(Document.source_doc == profile.source_doc)).scalar_one_or_none()
    metadata = dict(profile.metadata)
    metadata["text_sha256"] = _text_hash(text)
    if existing is None:
        document = Document(
            source_doc=profile.source_doc,
            title=profile.title,
            doc_type=profile.doc_type,
            source_path=str(profile.path),
            region=profile.region,
            branch=profile.branch,
            service_type=profile.service_type,
            metadata_json=metadata,
        )
        db.add(document)
        db.flush()
        return document.id
    existing.title = profile.title
    existing.doc_type = profile.doc_type
    existing.source_path = str(profile.path)
    existing.region = profile.region
    existing.branch = profile.branch
    existing.service_type = profile.service_type
    existing.metadata_json = metadata
    db.flush()
    return existing.id


def delete_existing_source_rows(db: Session, source_doc: str) -> None:
    existing = db.execute(select(Document).where(Document.source_doc == source_doc)).scalar_one_or_none()
    if existing is not None:
        db.execute(delete(Chunk).where(Chunk.document_id == existing.id))
    db.execute(delete(ServiceArea).where(ServiceArea.source_doc == source_doc))
    db.execute(delete(BranchHours).where(BranchHours.source_doc == source_doc))
    db.flush()


def persist_chunks(db: Session, document_id: int, chunks: Iterable[ChunkRecord]) -> None:
    for chunk in chunks:
        db.add(
            Chunk(
                document_id=document_id,
                chunk_text=chunk.chunk_text,
                source_doc=chunk.source_doc,
                page_number=chunk.page_number,
                section=chunk.section,
                doc_type=chunk.doc_type,
                region=chunk.region,
                branch=chunk.branch,
                service_type=chunk.service_type,
                policy_type=chunk.policy_type,
                effective_date=chunk.effective_date,
                search_vector=chunk.search_vector,
                embedding=chunk.embedding,
                metadata_json=chunk.metadata,
            )
        )


def persist_service_areas(db: Session, records: Iterable[ServiceAreaRecord], source_text: str) -> None:
    for record in records:
        db.add(
            ServiceArea(
                region=record.region,
                county=record.county,
                zip_start=record.zip_start,
                zip_end=record.zip_end,
                zip_exact=record.zip_exact,
                hvac_status=record.hvac_status,
                plumbing_status=record.plumbing_status,
                electrical_status=record.electrical_status,
                primary_branch=record.primary_branch,
                overflow_branch=record.overflow_branch,
                restriction_notes=record.restriction_notes or source_text[:1000],
                source_doc=record.source_doc,
            )
        )


def persist_branch_hours(db: Session, records: Iterable[BranchHoursRecord], source_text: str) -> None:
    for record in records:
        db.add(
            BranchHours(
                branch=record.branch,
                day_of_week=record.day_of_week,
                opens_at=record.opens_at,
                closes_at=record.closes_at,
                timezone=record.timezone,
                source_doc=record.source_doc,
                metadata_json=record.metadata,
            )
        )


def _text_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_directory(path: Path, db: Session | None = None, embedder: EmbeddingBackend | None = None) -> list[IngestionReport]:
    reports: list[IngestionReport] = []
    for pdf_path in sorted(path.glob("*.pdf")):
        reports.append(ingest_pdf_path(pdf_path, db=db, embedder=embedder))
    return reports


def rebuild_chunk_indexes(db: Session) -> None:
    db.execute(sa.text("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw"))
    db.execute(sa.text("DROP INDEX IF EXISTS ix_chunks_search_vector_gin"))
    db.execute(sa.text(build_hnsw_index_ddl()))
    db.execute(sa.text("CREATE INDEX ix_chunks_search_vector_gin ON chunks USING gin (search_vector)"))
    db.commit()
