from __future__ import annotations

from sqlalchemy.types import UserDefinedType

try:  # pragma: no cover - exercised in Docker with pgvector installed
    from pgvector.sqlalchemy import Vector as PGVector  # type: ignore
except Exception:  # pragma: no cover
    PGVector = None


class Vector(UserDefinedType):
    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"


def vector_type(dimensions: int):
    if PGVector is not None:
        return PGVector(dimensions)
    return Vector(dimensions)

