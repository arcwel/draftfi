"""Shared pytest fixtures."""
from __future__ import annotations

import os
import socket
import sqlite3
from pathlib import Path

import pytest

os.environ.setdefault("DRAFTFI_DB_PATH", ":memory:")
# Keep tests off the real OS keychain — key storage falls back to plaintext.
os.environ.setdefault("DRAFTFI_NO_KEYRING", "1")

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


_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", "::", ""}


def _host_of(address) -> str:
    if isinstance(address, tuple | list) and address:
        return str(address[0])
    return str(address)  # AF_UNIX path etc.


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch):
    """Fail any test that tries to reach a non-loopback host.

    Keeps the suite hermetic for unattended/offline runners: a regression that
    lets a test hit a real provider fails loudly instead of flaking. Loopback
    stays allowed (TestClient, the single-instance port lock, dead-port tests).
    """
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and (
            _host_of(address) not in _LOOPBACK
        ):
            raise RuntimeError(f"network blocked in tests: connect to {address!r}")
        return real_connect(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None and str(host) not in _LOOPBACK:
            raise RuntimeError(f"network blocked in tests: resolve {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
