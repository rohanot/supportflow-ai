from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def make_engine(settings: Settings | None = None) -> Engine:
    resolved = settings or get_settings()
    return create_engine(resolved.database_url, future=True)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    engine = make_engine()
    SessionLocal = make_sessionmaker(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_database(engine: Engine) -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True

