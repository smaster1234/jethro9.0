"""
Database Session Management
===========================

PostgreSQL connection handling with SQLAlchemy.
Supports both sync and async operations.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text, event
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
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
        )
        # Enforce foreign keys for SQLite
        def _enable_sqlite_fk(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        event.listen(engine, "connect", _enable_sqlite_fk)
        return engine

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
    _ensure_b1_schema(engine)
    _ensure_notebook_schema(engine)
    _ensure_credits_schema(engine)


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


def _ensure_b1_schema(engine) -> None:
    """
    Ensure B1 columns exist (lightweight migration).
    """
    try:
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("cases")}
        if "organization_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE cases ADD COLUMN organization_id VARCHAR(36)"))
    except Exception:
        pass


def _ensure_notebook_schema(engine) -> None:
    """
    Ensure Notebook-era columns exist (lightweight migration).
    Adds doc_class to documents table.
    Also cleans up any stale PostgreSQL native enum types that may have been
    created by an earlier model definition using Enum(DocClass).
    """
    try:
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("documents")}
        if "doc_class" not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE documents ADD COLUMN doc_class VARCHAR(20) DEFAULT 'supporting'"
                ))
    except Exception:
        pass

    # Clean up stale native enum types that conflict with VARCHAR columns
    for enum_name in ("docclass", "versionchangetype", "credittransactiontype"):
        try:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TYPE IF EXISTS {enum_name} CASCADE"))
        except Exception:
            pass


def _ensure_credits_schema(engine) -> None:
    """
    Ensure credit system columns exist (lightweight migration).
    The credit_ledger and user_credit_balances tables may have been created
    by an earlier schema version missing newer columns.
    """
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # --- credit_ledger ---
        if "credit_ledger" in tables:
            columns = {c["name"] for c in inspector.get_columns("credit_ledger")}
            with engine.begin() as conn:
                if "transaction_type" not in columns:
                    conn.execute(text(
                        "ALTER TABLE credit_ledger ADD COLUMN transaction_type VARCHAR(20) DEFAULT 'grant' NOT NULL"
                    ))
                if "balance_after" not in columns:
                    conn.execute(text(
                        "ALTER TABLE credit_ledger ADD COLUMN balance_after INTEGER DEFAULT 0 NOT NULL"
                    ))
                if "description" not in columns:
                    conn.execute(text(
                        "ALTER TABLE credit_ledger ADD COLUMN description VARCHAR(500)"
                    ))
                if "case_id" not in columns:
                    conn.execute(text(
                        "ALTER TABLE credit_ledger ADD COLUMN case_id VARCHAR(36)"
                    ))
                if "run_id" not in columns:
                    conn.execute(text(
                        "ALTER TABLE credit_ledger ADD COLUMN run_id VARCHAR(36)"
                    ))
                if "created_by" not in columns:
                    conn.execute(text(
                        "ALTER TABLE credit_ledger ADD COLUMN created_by VARCHAR(36)"
                    ))

        # --- user_credit_balances ---
        if "user_credit_balances" in tables:
            columns = {c["name"] for c in inspector.get_columns("user_credit_balances")}
            with engine.begin() as conn:
                if "total_granted" not in columns:
                    conn.execute(text(
                        "ALTER TABLE user_credit_balances ADD COLUMN total_granted INTEGER DEFAULT 0 NOT NULL"
                    ))
                if "total_consumed" not in columns:
                    conn.execute(text(
                        "ALTER TABLE user_credit_balances ADD COLUMN total_consumed INTEGER DEFAULT 0 NOT NULL"
                    ))
                if "last_transaction_at" not in columns:
                    conn.execute(text(
                        "ALTER TABLE user_credit_balances ADD COLUMN last_transaction_at TIMESTAMP"
                    ))
                if "updated_at" not in columns:
                    conn.execute(text(
                        "ALTER TABLE user_credit_balances ADD COLUMN updated_at TIMESTAMP"
                    ))

    except Exception:
        # Non-fatal: avoid breaking startup
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
