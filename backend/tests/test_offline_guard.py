"""The conftest network guard really blocks non-loopback traffic."""
from __future__ import annotations

import socket

import pytest


def test_non_loopback_connect_is_blocked():
    with socket.socket() as s, pytest.raises(RuntimeError, match="network blocked"):
        s.connect(("93.184.216.34", 80))


def test_dns_resolution_is_blocked():
    with pytest.raises(RuntimeError, match="network blocked"):
        socket.getaddrinfo("api.openai.com", 443)


def test_loopback_is_not_intercepted():
    # Reaches the real socket layer: an OSError (refused / interface down), never
    # the guard's RuntimeError.
    with socket.socket() as c, pytest.raises(OSError):
        c.connect(("127.0.0.1", 1))
