"""Data-access layer (CRUD) for categories, cache, transactions, branches.

All functions take an explicit ``sqlite3.Connection`` so they compose inside a
request scope or a test transaction. They never commit — the caller owns the
transaction boundary (see ``connection.session`` / ``get_db``).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
def list_categories(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return _rows(conn.execute("SELECT * FROM categories ORDER BY name").fetchall())


def get_category(conn: sqlite3.Connection, category_id: int) -> dict[str, Any] | None:
    return _row(
        conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    )


def get_category_by_name(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    return _row(
        conn.execute("SELECT * FROM categories WHERE name = ?", (name,)).fetchone()
    )


def upsert_category(conn: sqlite3.Connection, name: str, color: str = "#64748B") -> int:
    """Insert a category by name (idempotent) and return its id."""
    existing = get_category_by_name(conn, name)
    if existing:
        return int(existing["id"])
    cur = conn.execute(
        "INSERT INTO categories (name, color) VALUES (?, ?)", (name, color)
    )
    return int(cur.lastrowid)


# --------------------------------------------------------------------------- #
# Merchant LLM cache
# --------------------------------------------------------------------------- #
def get_cache(conn: sqlite3.Connection, raw_description: str) -> dict[str, Any] | None:
    return _row(
        conn.execute(
            "SELECT * FROM merchant_llm_cache WHERE raw_description = ?",
            (raw_description,),
        ).fetchone()
    )


def put_cache(
    conn: sqlite3.Connection,
    raw_description: str,
    clean_merchant: str,
    category_id: int | None,
) -> None:
    """Insert or replace a cache mapping (the deterministic dedupe rule)."""
    conn.execute(
        "INSERT INTO merchant_llm_cache (raw_description, clean_merchant, category_id) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(raw_description) DO UPDATE SET "
        "clean_merchant = excluded.clean_merchant, category_id = excluded.category_id",
        (raw_description, clean_merchant, category_id),
    )


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
def transaction_exists(conn: sqlite3.Connection, import_hash: str) -> bool:
    """True if a transaction with this content signature is already stored."""
    return (
        conn.execute(
            "SELECT 1 FROM transactions WHERE import_hash = ? LIMIT 1",
            (import_hash,),
        ).fetchone()
        is not None
    )


def insert_transaction(conn: sqlite3.Connection, tx: dict[str, Any]) -> int | None:
    """Insert a transaction; returns id, or None if deduped on import_hash."""
    try:
        cur = conn.execute(
            "INSERT INTO transactions "
            "(date, raw_description, amount, account_name, category_id, "
            " clean_merchant, resolution, import_hash) "
            "VALUES (:date, :raw_description, :amount, :account_name, :category_id, "
            ":clean_merchant, :resolution, :import_hash)",
            tx,
        )
        return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        # Duplicate import_hash — statement row already ingested.
        return None


def list_transactions(
    conn: sqlite3.Connection, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            "SELECT t.*, c.name AS category_name, c.color AS category_color "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    )


def count_transactions(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])


def get_transaction(conn: sqlite3.Connection, tx_id: int) -> dict[str, Any] | None:
    return _row(
        conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    )


def update_transaction_category(
    conn: sqlite3.Connection, tx_id: int, category_id: int, resolution: str = "override"
) -> None:
    conn.execute(
        "UPDATE transactions SET category_id = ?, resolution = ? WHERE id = ?",
        (category_id, resolution, tx_id),
    )


def apply_category_to_raw(
    conn: sqlite3.Connection, raw_description: str, category_id: int
) -> int:
    """Apply a category to every transaction sharing a raw descriptor.

    Returns the number of rows updated. Used by the user-override sync so a
    manual correction propagates to all past instances of that raw string.
    """
    cur = conn.execute(
        "UPDATE transactions SET category_id = ?, resolution = 'override' "
        "WHERE raw_description = ?",
        (category_id, raw_description),
    )
    return cur.rowcount


def category_totals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Aggregate signed amounts by category — feeds simulation baselines."""
    return _rows(
        conn.execute(
            "SELECT c.id AS category_id, c.name AS category_name, "
            "SUM(t.amount) AS total, COUNT(*) AS n "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "GROUP BY t.category_id"
        ).fetchall()
    )


def set_category_budget(
    conn: sqlite3.Connection, category_id: int, monthly_budget: float | None
) -> None:
    """Set (or clear, with None) a category's monthly budget target."""
    conn.execute(
        "UPDATE categories SET monthly_budget = ? WHERE id = ?",
        (monthly_budget, category_id),
    )


def months_observed(conn: sqlite3.Connection) -> int:
    """Distinct calendar months present in the transaction history (min 1)."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT substr(date, 1, 7)) AS n FROM transactions"
    ).fetchone()
    return max(1, int(row["n"] or 0))


def category_breakdown(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Per-category signed totals + counts joined with budget targets.

    Includes every category that has transactions; the caller derives monthly
    averages using ``months_observed``.
    """
    return _rows(
        conn.execute(
            "SELECT c.id AS category_id, c.name AS category_name, "
            "c.color AS category_color, c.monthly_budget AS monthly_budget, "
            "COALESCE(SUM(t.amount), 0) AS total, COUNT(t.id) AS n "
            "FROM categories c "
            "JOIN transactions t ON t.category_id = c.id "
            "GROUP BY c.id "
            "ORDER BY SUM(t.amount) ASC"
        ).fetchall()
    )


# --------------------------------------------------------------------------- #
# Branches (sandbox scenarios)
# --------------------------------------------------------------------------- #
def _decode_branch(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["parameters"] = json.loads(row.get("parameters") or "{}")
    row["milestones"] = json.loads(row.get("milestones") or "[]")
    row["is_base"] = bool(row.get("is_base"))
    return row


def list_branches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM branches ORDER BY is_base DESC, id ASC"
    ).fetchall()
    return [_decode_branch(dict(r)) for r in rows]


def get_branch(conn: sqlite3.Connection, branch_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
    return _decode_branch(dict(row)) if row else None


def get_base_branch(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM branches WHERE is_base = 1").fetchone()
    return _decode_branch(dict(row)) if row else None


def create_branch(
    conn: sqlite3.Connection,
    name: str,
    parameters: dict[str, Any],
    milestones: list[dict[str, Any]],
    is_base: bool = False,
) -> int:
    cur = conn.execute(
        "INSERT INTO branches (name, is_base, parameters, milestones) "
        "VALUES (?, ?, ?, ?)",
        (name, 1 if is_base else 0, json.dumps(parameters), json.dumps(milestones)),
    )
    return int(cur.lastrowid)


def update_branch(
    conn: sqlite3.Connection,
    branch_id: int,
    name: str | None = None,
    parameters: dict[str, Any] | None = None,
    milestones: list[dict[str, Any]] | None = None,
) -> None:
    fields, values = [], []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if parameters is not None:
        fields.append("parameters = ?")
        values.append(json.dumps(parameters))
    if milestones is not None:
        fields.append("milestones = ?")
        values.append(json.dumps(milestones))
    if not fields:
        return
    values.append(branch_id)
    conn.execute(f"UPDATE branches SET {', '.join(fields)} WHERE id = ?", values)


def delete_branch(conn: sqlite3.Connection, branch_id: int) -> None:
    conn.execute("DELETE FROM branches WHERE id = ? AND is_base = 0", (branch_id,))


# --------------------------------------------------------------------------- #
# App settings (local key-value store — LLM provider config + API keys)
# --------------------------------------------------------------------------- #
def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        return
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_settings_map(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM app_settings").fetchall()
    }
