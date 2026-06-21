from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import hashlib
import re

from app.config import get_settings

try:  # pragma: no cover - optional locally, required in Docker runtime
    from fastembed import TextEmbedding
except Exception:  # pragma: no cover
    TextEmbedding = None

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIMENSION = 384

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingRuntimeInfo:
    embedding_backend: str
    embedding_model: str
    embedding_dimension: int
    fallback_allowed: bool
    embedded_at: str


def normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]+", " ", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def fallback_embedding(text: str, dimensions: int = DEFAULT_EMBEDDING_DIMENSION) -> list[float]:
    values = [0.0] * dimensions
    tokens = normalize_text(text).split()
    if not tokens:
        return values
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for index in range(dimensions):
            values[index] += digest[index % len(digest)] / 255.0
    scale = max(len(tokens), 1)
    return [value / scale for value in values]


def build_embedding_runtime_info(
    embedding_backend: str,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION,
    fallback_allowed: bool = False,
) -> EmbeddingRuntimeInfo:
    return EmbeddingRuntimeInfo(
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        fallback_allowed=fallback_allowed,
        embedded_at=datetime.now(timezone.utc).isoformat(),
    )


def build_chunk_embedding_metadata(
    embedding_backend: str,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION,
    fallback_allowed: bool = False,
) -> dict[str, object]:
    runtime_info = build_embedding_runtime_info(
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        fallback_allowed=fallback_allowed,
    )
    return {
        "embedding_backend": runtime_info.embedding_backend,
        "embedding_model": runtime_info.embedding_model,
        "embedding_dimension": runtime_info.embedding_dimension,
        "fallback_allowed": runtime_info.fallback_allowed,
        "embedded_at": runtime_info.embedded_at,
    }


class FastEmbedBackend:
    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION,
        allow_fallback_embeddings: bool | None = None,
    ) -> None:
        settings = get_settings()
        fallback_allowed = settings.allow_fallback_embeddings if allow_fallback_embeddings is None else allow_fallback_embeddings
        self.embedding_model = model_name
        self.embedding_dimension = embedding_dimension
        self.fallback_allowed = fallback_allowed
        self.embedding_backend = "fastembed"
        self.embedded_at = datetime.now(timezone.utc).isoformat()

        if TextEmbedding is None:
            if not fallback_allowed:
                raise RuntimeError(
                    "FastEmbed is unavailable in the runtime and ALLOW_FALLBACK_EMBEDDINGS is false. "
                    "Install fastembed and onnxruntime, or enable fallback explicitly for tests."
                )
            self._embedder = None
            self.embedding_backend = "fallback"
        else:
            self._embedder = TextEmbedding(model_name=model_name)

        logger.info(
            "embedding runtime configured",
            extra={
                "embedding_backend": self.embedding_backend,
                "embedding_model": self.embedding_model,
                "embedding_dimension": self.embedding_dimension,
                "fallback_allowed": self.fallback_allowed,
            },
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._embedder is None:
            if not self.fallback_allowed:
                raise RuntimeError(
                    "FastEmbed backend is not available and fallback embeddings are disabled."
                )
            return [fallback_embedding(text, self.embedding_dimension) for text in texts]
        return [list(vector) for vector in self._embedder.embed(texts)]


def make_runtime_backend(allow_fallback_embeddings: bool | None = None) -> FastEmbedBackend:
    return FastEmbedBackend(allow_fallback_embeddings=allow_fallback_embeddings)
