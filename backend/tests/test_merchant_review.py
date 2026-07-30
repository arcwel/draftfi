"""The merchant review queue: one decision settles a merchant's whole history.

Correcting transactions one at a time does not scale — a real file had 3,887
unresolved transactions across 1,242 merchants, with the top 25 merchants
covering 1,169 of them. This queue exists to exploit that skew.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.db import repository as repo
from app.services import security


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A real app on a real file-backed DB.

    ":memory:" gives every connection its own empty database, so the test could
    not see what the app wrote — a file is what makes session() and the app agree.
    """
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(tmp_path / "review.db"))
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")
    importlib.reload(main)
    security.lock_session()
    security._passcode_set = False
    security._unlocked = True
    with TestClient(main.create_app()) as c:
        yield c


@pytest.fixture
def session():
    """Late import so it binds to the reloaded connection module."""
    from app.db.connection import session as _session

    return _session


def _add(conn, raw, i, *, amount=-10.0, resolution="uncategorized", key=None):
    from app.services import descriptors

    uncat = repo.upsert_category(conn, "Uncategorized", "#64748B")
    repo.insert_transaction(
        conn,
        {
            "date": f"2026-03-{(i % 28) + 1:02d}",
            "raw_description": raw,
            "amount": amount,
            "account_name": "Checking",
            "category_id": uncat,
            "clean_merchant": raw,
            "resolution": resolution,
            "import_hash": f"rev{i}",
        },
    )
    conn.execute(
        "UPDATE transactions SET canonical_key = ? WHERE import_hash = ?",
        (key or descriptors.canonical_key(raw), f"rev{i}"),
    )


def test_queue_ranks_merchants_by_transaction_count(client, session):
    """Working the list top-down is what makes this fast, so the order is the
    feature — not a display detail."""
    with session() as conn:
        for i in range(5):
            _add(conn, f"ZEPHYR CYCLES *{i}A PORTLAND OR", i)
        for i in range(2):
            _add(conn, f"QUINCE BAKEHOUSE *{i}B", 100 + i)
        _add(conn, "SOLO VENDOR ONCE", 200)
        conn.commit()

    page = client.get("/merchants/review").json()
    counts = [(r["display_name"], r["txn_count"]) for r in page["items"]]
    assert counts[0][1] == 5
    assert counts[0][0] == "Zephyr Cycles"
    assert [c for _, c in counts] == sorted(
        (c for _, c in counts), reverse=True
    ), "must be worst-first"
    assert page["total_merchants"] == 3
    assert page["total_transactions"] == 8


def test_descriptor_variants_collapse_to_one_row(client, session):
    """Five spellings of one merchant is ONE decision, not five."""
    with session() as conn:
        for i in range(5):
            _add(conn, f"ZEPHYR CYCLES *{i}XQ7 PORTLAND OR", i)
        conn.commit()

    page = client.get("/merchants/review").json()
    assert len(page["items"]) == 1
    assert page["items"][0]["txn_count"] == 5
    # A raw example comes along so an ambiguous name is still recognisable.
    assert "ZEPHYR" in page["items"][0]["sample_description"]


def test_one_decision_applies_to_every_transaction_for_that_merchant(client, session):
    with session() as conn:
        for i in range(4):
            _add(conn, f"ZEPHYR CYCLES *{i}A", i)
        shopping = repo.get_category_by_name(conn, "Shopping")
        conn.commit()
        shopping_id = int(shopping["id"])

    page = client.get("/merchants/review").json()
    key = page["items"][0]["canonical_key"]

    result = client.post(
        "/merchants/decisions",
        json={"decisions": [{"canonical_key": key, "category_id": shopping_id}]},
    ).json()
    assert result == {"merchants": 1, "transactions": 4}

    with session() as conn:
        rows = repo.list_transactions(conn)
        assert {r["category_name"] for r in rows} == {"Shopping"}
        # Recorded as the user's call, which outranks every automatic pass.
        decision = repo.get_merchant_decision(conn, key)
        assert decision["source"] == "user"


def test_decided_merchants_leave_the_queue(client, session):
    with session() as conn:
        for i in range(3):
            _add(conn, f"QUINCE BAKEHOUSE *{i}B", i)
        dining_id = int(repo.get_category_by_name(conn, "Dining")["id"])
        conn.commit()

    key = client.get("/merchants/review").json()["items"][0]["canonical_key"]
    client.post(
        "/merchants/decisions",
        json={"decisions": [{"canonical_key": key, "category_id": dining_id}]},
    )
    after = client.get("/merchants/review").json()
    assert after["items"] == []
    assert after["total_merchants"] == 0


def test_a_user_decision_is_not_offered_again_even_if_rows_stay_uncategorized(
    client, session
):
    """Guards the precedence rule: once the user has ruled on a merchant, the
    queue must not keep asking."""
    with session() as conn:
        _add(conn, "QUINCE BAKEHOUSE 1", 0)
        groceries_id = int(repo.get_category_by_name(conn, "Groceries")["id"])
        repo.put_merchant_decision(
            conn,
            canonical_key="QUINCE BAKEHOUSE",
            display_name="Quince Bakehouse",
            category_id=groceries_id,
            source="user",
        )
        conn.commit()

    assert client.get("/merchants/review").json()["items"] == []


def test_model_suggestions_are_shown_but_not_applied(client, session):
    """The model proposes; the user confirms. A suggestion must never silently
    become the answer."""
    with session() as conn:
        _add(conn, "ZEPHYR CYCLES 1", 0)
        travel_id = int(repo.get_category_by_name(conn, "Travel")["id"])
        repo.put_merchant_decision(
            conn,
            canonical_key="ZEPHYR CYCLES",
            display_name="Zephyr Cycles",
            category_id=travel_id,
            source="llm",
            confidence=0.61,
        )
        conn.commit()

    row = client.get("/merchants/review").json()["items"][0]
    assert row["suggested_category_id"] == travel_id
    assert row["suggestion_source"] == "llm"
    assert row["confidence"] == pytest.approx(0.61)

    with session() as conn:
        # Still uncategorized on the row itself — nothing was applied.
        assert repo.list_transactions(conn)[0]["category_name"] == "Uncategorized"


def test_a_bad_category_id_is_rejected_before_anything_is_written(client, session):
    with session() as conn:
        _add(conn, "ZEPHYR CYCLES 1", 0)
        conn.commit()

    key = client.get("/merchants/review").json()["items"][0]["canonical_key"]
    response = client.post(
        "/merchants/decisions",
        json={"decisions": [{"canonical_key": key, "category_id": 99999}]},
    )
    assert response.status_code == 400
    with session() as conn:
        assert repo.get_merchant_decision(conn, key) is None


def test_empty_batch_is_a_noop(client):
    assert client.post("/merchants/decisions", json={"decisions": []}).json() == {
        "merchants": 0,
        "transactions": 0,
    }


def test_already_categorized_merchants_are_not_in_the_queue(client, session):
    with session() as conn:
        dining_id = int(repo.get_category_by_name(conn, "Dining")["id"])
        _add(conn, "QUINCE BAKEHOUSE 1", 0, resolution="rule")
        conn.execute(
            "UPDATE transactions SET category_id = ? WHERE import_hash = 'rev0'",
            (dining_id,),
        )
        conn.commit()

    assert client.get("/merchants/review").json()["items"] == []
