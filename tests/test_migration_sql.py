from __future__ import annotations

from sqlalchemy import create_mock_engine

from app.db.models import Base


def test_metadata_compiles_for_postgres() -> None:
    emitted: list[str] = []

    def capture(sql, *_, **__):
        emitted.append(str(sql))

    engine = create_mock_engine("postgresql+psycopg://", capture)
    Base.metadata.create_all(engine)

    joined = "\n".join(emitted)
    assert "documents" in joined
    assert "chunks" in joined
    assert "vector" in joined.lower()

