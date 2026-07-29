"""SQLAlchemy setup and database lifecycle helpers."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import PROJECT_ROOT, settings


def resolved_database_url(database_url: str) -> str:
    """Make the default relative SQLite URL stable regardless of the launch CWD."""

    prefix = "sqlite:///./"
    if database_url.startswith(prefix):
        relative_path = database_url.removeprefix(prefix)
        return f"sqlite:///{(PROJECT_ROOT / relative_path).as_posix()}"
    return database_url


def build_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


class Base(DeclarativeBase):
    pass


DATABASE_URL = resolved_database_url(settings.database_url)
if DATABASE_URL.startswith("sqlite:///"):
    database_path = DATABASE_URL[len("sqlite:///"):]
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine = build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    """Create the local development schema. Migrations replace this in production."""

    # Import models before metadata creation so all tables are registered.
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
