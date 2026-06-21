from __future__ import annotations

import pytest

from app.rag.embeddings import FastEmbedBackend, build_chunk_embedding_metadata, DEFAULT_EMBEDDING_MODEL


class FakeTextEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.25 for _ in range(384)] for _ in texts]


def test_fastembed_backend_uses_fastembed_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.embeddings.TextEmbedding", FakeTextEmbedding, raising=False)

    backend = FastEmbedBackend()
    vector = backend.embed(["hello world"])[0]

    assert backend.embedding_backend == "fastembed"
    assert backend.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert len(vector) == 384
    assert vector[0] == 0.25


def test_fastembed_backend_requires_runtime_dependency_when_fallback_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.embeddings.TextEmbedding", None, raising=False)

    with pytest.raises(RuntimeError, match="FastEmbed is unavailable"):
        FastEmbedBackend(allow_fallback_embeddings=False)


def test_fastembed_backend_allows_explicit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.embeddings.TextEmbedding", None, raising=False)

    backend = FastEmbedBackend(allow_fallback_embeddings=True)
    vector = backend.embed(["hello world"])[0]

    assert len(vector) == 384
    assert backend.embedding_backend == "fallback"


def test_embedding_metadata_is_traceable() -> None:
    metadata = build_chunk_embedding_metadata(
        embedding_backend="fastembed",
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        embedding_dimension=384,
        fallback_allowed=False,
    )

    assert metadata["embedding_backend"] == "fastembed"
    assert metadata["embedding_dimension"] == 384
    assert metadata["embedded_at"]
