"""G2 — app passcode + lock gate. G4 — currency/locale preferences."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.services import security


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "sec.db"
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(db_file))
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")
    importlib.reload(main)
    # Each app starts unlocked with a fresh empty DB.
    security.lock_session()
    security._passcode_set = False
    security._unlocked = True
    with TestClient(main.create_app(), base_url="http://127.0.0.1") as c:
        yield c


# --------------------------------------------------------------------------- #
# G2 — passcode + lock
# --------------------------------------------------------------------------- #
def test_no_passcode_by_default(client):
    status = client.get("/security").json()
    assert status["passcode_set"] is False
    assert status["locked"] is False
    # Data routes are open with no passcode.
    assert client.get("/categories").status_code == 200


def test_passcode_gate_blocks_then_unlock_opens(client):
    r = client.post("/security/passcode", json={"passcode": "1234"})
    assert r.status_code == 200
    assert r.json()["passcode_set"] is True

    # Simulate a fresh launch: a configured passcode starts the session locked.
    security.lock_session()
    assert client.get("/security").json()["locked"] is True
    # Protected data routes are refused while locked...
    assert client.get("/categories").status_code == 423
    # ...but the lock screen's own endpoints stay reachable.
    assert client.get("/health").status_code == 200
    assert client.get("/security").status_code == 200

    # Wrong passcode stays locked; correct one opens everything.
    assert client.post("/security/unlock", json={"passcode": "0000"}).json()["ok"] is False
    assert client.get("/categories").status_code == 423
    assert client.post("/security/unlock", json={"passcode": "1234"}).json()["ok"] is True
    assert client.get("/categories").status_code == 200


def test_change_and_clear_require_current_passcode(client):
    client.post("/security/passcode", json={"passcode": "1111"})
    # Changing without the correct current passcode is rejected.
    bad = client.post("/security/passcode", json={"passcode": "2222", "current": "9999"})
    assert bad.status_code == 403
    ok = client.post("/security/passcode", json={"passcode": "2222", "current": "1111"})
    assert ok.status_code == 200
    # Clearing needs the (new) current passcode too.
    assert client.post("/security/passcode/clear", json={"current": "1111"}).status_code == 403
    cleared = client.post("/security/passcode/clear", json={"current": "2222"})
    assert cleared.status_code == 200
    assert cleared.json()["passcode_set"] is False


def test_passcode_is_hashed_not_stored_plaintext(client):
    client.post("/security/passcode", json={"passcode": "hunter2"})
    from app.db import repository as repo
    from app.db.connection import session
    from app.services import preferences  # noqa: F401 (ensure app import works)

    with session() as conn:
        stored = repo.get_setting(conn, security.K_PASSCODE)
    assert stored is not None
    assert "hunter2" not in stored
    assert stored.startswith("pbkdf2$")


# --------------------------------------------------------------------------- #
# G4 — preferences
# --------------------------------------------------------------------------- #
def test_preferences_default_and_update(client):
    prefs = client.get("/preferences").json()
    assert prefs == {
        "currency": "USD",
        "locale": "en-US",
        "text_scale": 0,
        "ledger_columns": {},
    }

    updated = client.put("/preferences", json={"currency": "EUR", "locale": "de-DE"})
    assert updated.status_code == 200
    assert updated.json()["currency"] == "EUR"
    assert updated.json()["locale"] == "de-DE"
    # Persisted for the next read.
    assert client.get("/preferences").json()["currency"] == "EUR"


def test_ledger_column_widths_round_trip(client):
    updated = client.put(
        "/preferences", json={"ledger_columns": {"raw": 420, "date": 90}}
    )
    assert updated.status_code == 200
    assert updated.json()["ledger_columns"] == {"raw": 420, "date": 90}
    assert client.get("/preferences").json()["ledger_columns"] == {
        "raw": 420,
        "date": 90,
    }
    # Updating something else must not wipe the saved layout.
    client.put("/preferences", json={"currency": "GBP"})
    assert client.get("/preferences").json()["ledger_columns"] == {
        "raw": 420,
        "date": 90,
    }


def test_ledger_column_widths_are_clamped(client):
    """Nothing stored here may render a column too narrow to see or absurdly
    wide — the frontend clamps too, but the API is the durable boundary."""
    from app.services.preferences import MAX_COLUMN_WIDTH, MIN_COLUMN_WIDTH

    client.put("/preferences", json={"ledger_columns": {"raw": 99999, "date": -5}})
    stored = client.get("/preferences").json()["ledger_columns"]
    assert stored == {"raw": MAX_COLUMN_WIDTH, "date": MIN_COLUMN_WIDTH}


def test_malformed_stored_layout_degrades_to_empty(client):
    """The whole UI boots through /preferences, so a bad row must not 500 it."""
    from app.db import repository as repo
    from app.db.connection import session
    from app.services import preferences as prefs_service

    with session() as conn:
        repo.set_setting(conn, prefs_service.K_LEDGER_COLUMNS, "{not json")
        conn.commit()
    response = client.get("/preferences")
    assert response.status_code == 200
    assert response.json()["ledger_columns"] == {}


def test_text_scale_persists_and_is_clamped(client):
    assert client.put("/preferences", json={"text_scale": 6}).json()["text_scale"] == 6
    assert client.get("/preferences").json()["text_scale"] == 6
    # Out-of-range values are rejected by validation (0-10).
    assert client.put("/preferences", json={"text_scale": 25}).status_code == 422
    assert client.put("/preferences", json={"text_scale": -1}).status_code == 422
    # Updating currency alone leaves the scale intact.
    client.put("/preferences", json={"currency": "GBP"})
    assert client.get("/preferences").json()["text_scale"] == 6
