"""F2 — single-instance guard for the desktop launcher."""
from __future__ import annotations

import desktop


def test_single_instance_lock_is_exclusive():
    """The first bind holds the lock; a concurrent second bind is refused."""
    first = desktop._acquire_single_instance()
    assert first is not None
    try:
        assert desktop._acquire_single_instance() is None
    finally:
        first.close()

    # Once released, the lock can be acquired again (relaunch after quit).
    again = desktop._acquire_single_instance()
    assert again is not None
    again.close()
