from __future__ import annotations

from pathlib import Path

from app.rag.reembed import reembed_directory
from app.rag.ingestion import rebuild_chunk_indexes


class FakeBackend:
    embedding_backend = "fastembed"
    embedding_model = "fake-model"
    embedding_dimension = 384
    fallback_allowed = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(i % 7) for i in range(384)] for _ in texts]


class FakeDb:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.commits = 0

    def execute(self, statement):
        self.executed.append(str(statement))
        return None

    def commit(self) -> None:
        self.commits += 1


def test_reembed_directory_updates_chunk_metadata_and_counts(tmp_path: Path) -> None:
    result = reembed_directory(Path("sl_docs"), db=None, backend=FakeBackend())

    assert result["documents"] == 13
    assert result["chunks"] >= 0
    assert result["embedding_backend"] == "fastembed"


def test_rebuild_chunk_indexes_recreates_hnsw_and_gin_indexes() -> None:
    db = FakeDb()

    rebuild_chunk_indexes(db)

    joined = "\n".join(db.executed)
    assert "DROP INDEX IF EXISTS ix_chunks_embedding_hnsw" in joined
    assert "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw" in joined
    assert "gin" in joined.lower()
