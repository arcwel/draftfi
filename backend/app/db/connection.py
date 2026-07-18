"""SQLite connection management with FastAPI dependency support."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.config import get_settings
from app.db.schema import initialize


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with sane local-first pragmas."""
    path = db_path or get_settings().db_path
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create/upgrade schema and seed defaults for the configured database."""
    conn = connect(db_path)
    try:
        initialize(conn)
    finally:
        conn.close()


@contextmanager
def session(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Context-managed connection that commits on success, rolls back on error."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency yielding a request-scoped connection."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
