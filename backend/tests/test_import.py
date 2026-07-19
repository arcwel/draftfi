"""Imports are additive and non-destructive.

Guarantees:
* Re-importing the same data adds nothing (even under a different filename).
* An overlapping statement adds only the genuinely new rows.
* Existing rows — including manual category overrides — are never touched.
"""
from __future__ import annotations

import importlib
import time

import pytest
from fastapi.testclient import TestClient

# A statement with NO account column, so dedupe cannot lean on it.
CSV_A = (
    b"Date,Description,Amount\n"
    b"2026-01-05,COFFEE BAR,-4.50\n"
    b"2026-01-06,GROCERY MART,-62.10\n"
    b"2026-01-07,PAYCHECK,2000.00\n"
)
# Overlaps CSV_A on the first two rows, adds one new row.
CSV_B = (
    b"Date,Description,Amount\n"
    b"2026-01-05,COFFEE BAR,-4.50\n"
    b"2026-01-06,GROCERY MART,-62.10\n"
    b"2026-01-09,BOOKSTORE,-30.00\n"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "imp.db"
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(db_file))
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")
    importlib.reload(main)

    # No live LLM in tests.
    from app.services import llm

    async def offline(cfg):
        return False, None, "offline"

    monkeypatch.setattr(llm, "health", offline)

    with TestClient(main.create_app()) as c:
        yield c


def _import(client, content, filename="statement.csv", account=""):
    """Kick off an import and poll its background job to completion."""
    r = client.post(
        "/import/csv",
        files={"file": (filename, content, "text/csv")},
        data={"account_name": account},
    )
    job_id = r.json()["job_id"]
    for _ in range(200):
        status = client.get(f"/import/status/{job_id}").json()
        if status["state"] in ("done", "error"):
            return status
        time.sleep(0.02)
    raise AssertionError("import did not finish in time")


def test_reimport_same_data_is_noop(client):
    first = _import(client, CSV_A)
    assert first["imported"] == 3
    assert first["skipped_duplicates"] == 0

    second = _import(client, CSV_A)
    assert second["imported"] == 0
    assert second["skipped_duplicates"] == 3
    assert client.get("/transactions").json()["total"] == 3


def test_reimport_under_different_filename_still_dedupes(client):
    _import(client, CSV_A, filename="january.csv")
    # Same data, different filename — must NOT create duplicates.
    again = _import(client, CSV_A, filename="jan-2026 (1).csv")
    assert again["imported"] == 0
    assert again["skipped_duplicates"] == 3
    assert client.get("/transactions").json()["total"] == 3


def test_overlapping_statement_adds_only_new_rows(client):
    _import(client, CSV_A)
    overlap = _import(client, CSV_B)
    assert overlap["imported"] == 1          # only BOOKSTORE is new
    assert overlap["skipped_duplicates"] == 2
    assert client.get("/transactions").json()["total"] == 4


def test_override_survives_reimport(client):
    _import(client, CSV_A)
    tx = next(
        t
        for t in client.get("/transactions").json()["items"]
        if "GROCERY" in t["raw_description"]
    )
    groceries = next(
        c for c in client.get("/categories").json() if c["name"] == "Groceries"
    )
    client.patch(
        f"/transactions/{tx['id']}/category", json={"category_id": groceries["id"]}
    )

    # Re-import the same statement — the override must be preserved.
    _import(client, CSV_A)
    after = next(
        t
        for t in client.get("/transactions").json()["items"]
        if t["id"] == tx["id"]
    )
    assert after["category_name"] == "Groceries"
    assert after["resolution"] == "override"
    assert client.get("/transactions").json()["total"] == 3
