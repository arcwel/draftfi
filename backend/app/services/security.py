"""Optional app passcode + a process-level lock (G2).

The passcode is stored only as a salted PBKDF2 hash. Because DraftFi is a
single-process local app, "locked" state lives in memory: the server starts
locked whenever a passcode is set, and API data routes are refused with 423
until :func:`unlock` succeeds. This gates the actual data, not just the UI.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from app.db import repository as repo

K_PASSCODE = "passcode_hash"  # "pbkdf2$<iters>$<salt_hex>$<hash_hex>"
_ITERATIONS = 200_000

# Path prefixes reachable before unlocking: the SPA shell + the endpoints the
# lock screen itself needs. Everything else is refused while locked.
_ALLOW_PREFIXES = ("/assets", "/security", "/health", "/update-check", "/favicon")
_ALLOW_EXACT = ("/", "")

# In-memory lock state for this process (avoids a DB hit on every request).
# `_passcode_set` mirrors whether a hash exists; `_unlocked` is the session flag.
_passcode_set = False
_unlocked = True


def _hash(passcode: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", passcode.encode("utf-8"), salt, _ITERATIONS
    ).hex()


def has_passcode(conn: sqlite3.Connection) -> bool:
    return bool(repo.get_setting(conn, K_PASSCODE))


def set_passcode(conn: sqlite3.Connection, passcode: str) -> None:
    global _passcode_set
    salt = secrets.token_bytes(16)
    stored = f"pbkdf2${_ITERATIONS}${salt.hex()}${_hash(passcode, salt)}"
    repo.set_setting(conn, K_PASSCODE, stored)
    _passcode_set = True
    unlock_session()  # you just set it while using the app — stay unlocked


def clear_passcode(conn: sqlite3.Connection) -> None:
    global _passcode_set
    repo.set_setting(conn, K_PASSCODE, None)
    _passcode_set = False
    unlock_session()


def verify(conn: sqlite3.Connection, passcode: str) -> bool:
    stored = repo.get_setting(conn, K_PASSCODE)
    if not stored:
        return False
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        candidate = hashlib.pbkdf2_hmac(
            "sha256", passcode.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, hash_hex)


def unlock_session() -> None:
    global _unlocked
    _unlocked = True


def lock_session() -> None:
    global _unlocked
    _unlocked = False


def is_locked() -> bool:
    """Locked only when a passcode exists AND this session hasn't unlocked."""
    return _passcode_set and not _unlocked


def refresh_lock_state(conn: sqlite3.Connection) -> None:
    """Called at startup: begin locked if a passcode is configured."""
    global _passcode_set, _unlocked
    _passcode_set = has_passcode(conn)
    _unlocked = not _passcode_set


def path_allowed_when_locked(path: str) -> bool:
    return path in _ALLOW_EXACT or path.startswith(_ALLOW_PREFIXES)
