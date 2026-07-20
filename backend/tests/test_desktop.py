"""F2 — single-instance guard for the desktop launcher."""
from __future__ import annotations

import socket

import desktop


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_single_instance_lock_is_exclusive():
    """The first bind holds the lock; a concurrent second bind is refused."""
    port = _free_port()  # a private port so the test never collides with a real app
    first = desktop._acquire_single_instance(port)
    assert first is not None
    try:
        assert desktop._acquire_single_instance(port) is None
    finally:
        first.close()

    # Once released, the lock can be acquired again (relaunch after quit).
    again = desktop._acquire_single_instance(port)
    assert again is not None
    again.close()
