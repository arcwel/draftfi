"""Shared pytest fixtures."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("DRAFTFI_DB_PATH", ":memory:")
# Keep tests off the real OS keychain — key storage falls back to plaintext.
os.environ.setdefault("DRAFTFI_NO_KEYRING", "1")
# Keep tests out of the user's real log file. Anything that builds the app
# (TestClient triggers the lifespan) configures logging, and without this the
# suite appends its own noise — 429s, "boom", fake keychain errors — to the file
# a user would attach to a bug report.
os.environ.setdefault(
    "DRAFTFI_LOG_DIR", tempfile.mkdtemp(prefix="draftfi-test-logs-")
)

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def conn() -> sqlite3.Connection:
    """An initialized in-memory database, torn down per test."""
    from app.db.schema import initialize

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    yield connection
    connection.close()


@pytest.fixture
def sample_csv():
    def _read(name: str) -> bytes:
        return (SAMPLE_DIR / name).read_bytes()

    return _read
