"""App passcode + display preferences endpoints (G2, G4)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import get_db
from app.models.schemas import (
    PasscodeClear,
    PasscodeSet,
    Preferences,
    PreferencesUpdate,
    SecurityStatus,
    UnlockRequest,
    UnlockResult,
)
from app.services import preferences, security

router = APIRouter(tags=["settings"])


# --------------------------------------------------------------------------- #
# Security (G2)
# --------------------------------------------------------------------------- #
@router.get("/security", response_model=SecurityStatus)
def security_status(conn: sqlite3.Connection = Depends(get_db)) -> SecurityStatus:
    return SecurityStatus(
        passcode_set=security.has_passcode(conn), locked=security.is_locked()
    )


@router.post("/security/passcode", response_model=SecurityStatus)
def set_passcode(
    body: PasscodeSet,
    conn: sqlite3.Connection = Depends(get_db),
) -> SecurityStatus:
    """Set or change the passcode (changing requires the current one)."""
    if security.has_passcode(conn) and not security.verify(conn, body.current or ""):
        raise HTTPException(status_code=403, detail="Current passcode is incorrect.")
    security.set_passcode(conn, body.passcode)
    conn.commit()
    return SecurityStatus(passcode_set=True, locked=security.is_locked())


@router.post("/security/passcode/clear", response_model=SecurityStatus)
def clear_passcode(
    body: PasscodeClear,
    conn: sqlite3.Connection = Depends(get_db),
) -> SecurityStatus:
    if not security.has_passcode(conn):
        return SecurityStatus(passcode_set=False, locked=False)
    if not security.verify(conn, body.current):
        raise HTTPException(status_code=403, detail="Current passcode is incorrect.")
    security.clear_passcode(conn)
    conn.commit()
    return SecurityStatus(passcode_set=False, locked=False)


@router.post("/security/unlock", response_model=UnlockResult)
def unlock(
    body: UnlockRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> UnlockResult:
    if security.verify(conn, body.passcode):
        security.unlock_session()
        return UnlockResult(ok=True)
    return UnlockResult(ok=False)


# --------------------------------------------------------------------------- #
# Preferences (G4)
# --------------------------------------------------------------------------- #
@router.get("/preferences", response_model=Preferences)
def get_preferences(conn: sqlite3.Connection = Depends(get_db)) -> Preferences:
    return Preferences(**preferences.get_preferences(conn))


@router.put("/preferences", response_model=Preferences)
def update_preferences(
    body: PreferencesUpdate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Preferences:
    prefs = preferences.set_preferences(conn, body.currency, body.locale)
    conn.commit()
    return Preferences(**prefs)
