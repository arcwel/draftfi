"""Shared pytest fixtures."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("DRAFTFI_DB_PATH", ":memory:")

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
