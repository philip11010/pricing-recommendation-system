"""
Engine and session management.

``DATABASE_URL`` is read from the environment, falling back to a local SQLite
file. ``python-dotenv`` loads ``.env`` if one is present, without overriding a
variable already set in the environment, so a deployment or a test can point
the application at a different database without editing any file.

The engine is created lazily and cached. Importing this module therefore does
not touch the filesystem, which matters because a module-level engine would
create ``app.db`` in whatever directory happened to be current, including
during a test run.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import PROJECT_ROOT
from src.db.models import Base

DEFAULT_DATABASE_URL = "sqlite:///./app.db"
ENV_FILE = PROJECT_ROOT / ".env"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def database_url() -> str:
    """
    The configured database URL.

    Resolution order: an existing ``DATABASE_URL`` environment variable,
    then ``DATABASE_URL`` in ``.env``, then the SQLite default. ``.env`` is
    loaded with ``override=False`` so the real environment always wins.
    """
    load_dotenv(ENV_FILE, override=False)
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def create_db_engine(url: str | None = None) -> Engine:
    """
    Build an engine for ``url``, defaulting to :func:`database_url`.

    SQLite gets ``check_same_thread=False`` because FastAPI runs synchronous
    endpoints on a worker threadpool, so a connection is not guaranteed to be
    used by the thread that opened it. Any parent directory named in a SQLite
    file URL is created, so pointing the app at a fresh directory works.
    """
    url = url or database_url()
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        _ensure_sqlite_directory(url)
    return create_engine(url, future=True, **kwargs)


def _ensure_sqlite_directory(url: str) -> None:
    path = url.removeprefix("sqlite:///")
    if path and path != ":memory:":
        parent = Path(path).expanduser().parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    """The cached process-wide engine, created on first use."""
    global _engine, _session_factory
    if _engine is None:
        _engine = create_db_engine()
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """
    Drop the cached engine and session factory.

    Called by tests after pointing ``DATABASE_URL`` at a temporary file, so
    the next :func:`get_engine` picks up the new setting. Not used in normal
    operation.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_session_factory() -> sessionmaker[Session]:
    """Session factory bound to the cached engine."""
    get_engine()
    assert _session_factory is not None  # set by get_engine
    return _session_factory


def init_db() -> None:
    """
    Create any missing tables.

    Called once at application startup. ``create_all`` is a no-op for tables
    that already exist, so it is safe on every boot. It does not alter an
    existing table, which is acceptable at prototype stage: there is no
    migration tool yet, and the schema is recorded in ``src/db/models.py``.
    """
    Base.metadata.create_all(bind=get_engine())


def get_session() -> Iterator[Session]:
    """
    FastAPI dependency yielding a session that is closed after the request.

    Endpoints commit explicitly, so that a handler which raises leaves
    nothing half-written.
    """
    with get_session_factory()() as session:
        yield session
