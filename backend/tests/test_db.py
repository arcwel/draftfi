"""Phase 1.7 — schema constraints, FK integrity, unique/index behavior."""
from __future__ import annotations

import sqlite3

import pytest

from app.db import repository as repo


def test_default_categories_seeded(conn):
    names = {c["name"] for c in repo.list_categories(conn)}
    assert {"Groceries", "Housing", "Uncategorized"} <= names


def test_category_name_unique(conn):
    conn.execute("INSERT INTO categories (name, color) VALUES ('X', '#000')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO categories (name, color) VALUES ('X', '#111')")


def test_upsert_category_idempotent(conn):
    a = repo.upsert_category(conn, "Coffee", "#111")
    b = repo.upsert_category(conn, "Coffee", "#222")
    assert a == b


def test_cache_upsert_replaces(conn):
    cat = repo.upsert_category(conn, "Shopping", "#333")
    repo.put_cache(conn, "AMZN MKTP", "Amazon", cat)
    repo.put_cache(conn, "AMZN MKTP", "Amazon.com", cat)
    cached = repo.get_cache(conn, "AMZN MKTP")
    assert cached["clean_merchant"] == "Amazon.com"


def test_transaction_dedupe_on_import_hash(conn):
    tx = {
        "date": "2026-01-01",
        "raw_description": "COFFEE",
        "amount": -3.5,
        "account_name": "Checking",
        "category_id": None,
        "clean_merchant": "Cafe",
        "resolution": "llm",
        "import_hash": "abc123",
    }
    first = repo.insert_transaction(conn, dict(tx))
    second = repo.insert_transaction(conn, dict(tx))
    assert first is not None
    assert second is None
    assert repo.count_transactions(conn) == 1


def test_apply_category_to_raw_propagates(conn):
    cat_a = repo.upsert_category(conn, "Dining", "#a")
    cat_b = repo.upsert_category(conn, "Groceries2", "#b")
    for i in range(3):
        repo.insert_transaction(
            conn,
            {
                "date": f"2026-01-0{i + 1}",
                "raw_description": "TRADER JOES",
                "amount": -20.0,
                "account_name": "Checking",
                "category_id": cat_a,
                "clean_merchant": "Trader Joe's",
                "resolution": "llm",
                "import_hash": f"h{i}",
            },
        )
    updated = repo.apply_category_to_raw(conn, "TRADER JOES", cat_b)
    assert updated == 3
    rows = conn.execute(
        "SELECT category_id, resolution FROM transactions"
    ).fetchall()
    assert all(r["category_id"] == cat_b and r["resolution"] == "override" for r in rows)


def test_fk_set_null_on_category_delete(conn):
    cat = repo.upsert_category(conn, "Temp", "#c")
    repo.insert_transaction(
        conn,
        {
            "date": "2026-01-01",
            "raw_description": "X",
            "amount": -1.0,
            "account_name": "A",
            "category_id": cat,
            "clean_merchant": "X",
            "resolution": "llm",
            "import_hash": "z1",
        },
    )
    conn.execute("DELETE FROM categories WHERE id = ?", (cat,))
    row = conn.execute("SELECT category_id FROM transactions").fetchone()
    assert row["category_id"] is None


def test_migrations_idempotent_after_interruption():
    """A migration interrupted after applying an ADD COLUMN must be re-runnable
    (no 'duplicate column name' brick on the next launch)."""
    from app.db import schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema.apply_migrations(conn)  # bring fully up to date

    # Simulate an interrupted migration 6: its column exists, but its version
    # row was never recorded (process died before the commit).
    conn.execute("DELETE FROM schema_migrations WHERE version >= 6")
    # budget_rollover (migration 6) is already present from the first run.

    # Re-running must tolerate the duplicate column and finish cleanly.
    schema.apply_migrations(conn)
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations")]
    assert max(versions) == max(v for v, _, _ in schema.MIGRATIONS)
    conn.close()
