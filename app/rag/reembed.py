from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.rag.embeddings import FastEmbedBackend
from app.rag.ingestion import ingest_directory


def reembed_directory(
    source_dir: Path,
    db: Session | None = None,
    backend: FastEmbedBackend | None = None,
) -> dict[str, object]:
    settings = get_settings()
    resolved_backend = backend or FastEmbedBackend(allow_fallback_embeddings=settings.allow_fallback_embeddings)
    reports = ingest_directory(source_dir, db=db, embedder=resolved_backend)
    summary = {
        "documents": len(reports),
        "chunks": sum(report.chunk_count for report in reports),
        "service_areas": sum(report.service_area_count for report in reports),
        "branch_hours": sum(report.branch_hours_count for report in reports),
        "embeddings": sum(report.embedding_count for report in reports),
        "embedding_backend": getattr(resolved_backend, "embedding_backend", "fastembed"),
        "embedding_model": getattr(resolved_backend, "embedding_model", "unknown"),
        "embedding_dimension": getattr(resolved_backend, "embedding_dimension", 0),
        "embedded_at": getattr(resolved_backend, "embedded_at", None),
    }
    return summary
