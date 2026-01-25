"""
Database Session Management
===========================

PostgreSQL connection handling with SQLAlchemy.
Supports both sync and async operations.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from .models import Base

_engine = None
_engine_url = None

# Session factory is configured lazily (important for tests that set DATABASE_URL at runtime).
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def _current_database_url() -> str:
    # Default to SQLite for development/testing, use DATABASE_URL for production PostgreSQL
    return os.environ.get("DATABASE_URL", "sqlite:///./dev.db")


def _create_engine_for_url(database_url: str):
    # For SQLite fallback in tests
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
        )

    return create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        # Prevent long hangs during cold starts / DB outages (Railway healthchecks)
        connect_args={
            "connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", "5")),
        },
        echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
    )


def get_engine():
    """Get the SQLAlchemy engine"""
    global _engine, _engine_url
    database_url = _current_database_url()
    if _engine is None or _engine_url != database_url:
        _engine = _create_engine_for_url(database_url)
        _engine_url = database_url
        SessionLocal.configure(bind=_engine)
    return _engine


def reset_engine():
    """Reset engine/sessionmaker (primarily for tests)."""
    global _engine, _engine_url
    _engine = None
    _engine_url = None
    SessionLocal.configure(bind=None)


def init_db():
    """Initialize database tables"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_phase2_schema(engine)


def _ensure_phase2_schema(engine) -> None:
    """
    Ensure Phase 2 columns exist (lightweight migration).
    """
    try:
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("claims")}
        if "witness_version_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE claims ADD COLUMN witness_version_id VARCHAR(36)"))
    except Exception:
        # Non-fatal: avoid breaking startup if ALTER isn't supported
        pass


def drop_db():
    """Drop all database tables (use with caution!)"""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database session.

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    # Ensure SessionLocal is configured for current DATABASE_URL
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database session.

    Usage:
        with get_db_session() as db:
            db.query(User).all()
    """
    # Ensure SessionLocal is configured for current DATABASE_URL
    get_engine()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class DatabaseManager:
    """
    Manager class for database operations.
    Useful for non-FastAPI contexts like workers.
    """

    def __init__(self, session: Session = None):
        self._session = session
        self._owns_session = session is None

    def __enter__(self):
        if self._owns_session:
            self._session = SessionLocal()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_session and self._session:
            if exc_type:
                self._session.rollback()
            else:
                self._session.commit()
            self._session.close()

    @property
    def session(self) -> Session:
        return self._session

    def commit(self):
        self._session.commit()

    def rollback(self):
        self._session.rollback()
