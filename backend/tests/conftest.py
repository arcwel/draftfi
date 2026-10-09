"""Shared pytest fixtures."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("DRAFTFI_DB_PATH", ":memory:")
# Keep tests off the real OS keychain — key storage falls back to plaintext.
os.environ.setdefault("DRAFTFI_NO_KEYRING", "1")

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch):
    """Fail loudly if any test tries to reach a non-loopback host.

    Keeps the suite deterministic on an unattended/offline runner: LLM and HTTP
    calls must be faked, never real.
    """
    import socket

    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else None
        if host is not None and host not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError(f"Outbound network blocked in tests: {address!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


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
