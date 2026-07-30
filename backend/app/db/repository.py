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
# Merchant decisions (canonical-key memo)
# --------------------------------------------------------------------------- #
def get_merchant_decision(
    conn: sqlite3.Connection, canonical_key: str
) -> dict[str, Any] | None:
    """The standing decision for a merchant, or None."""
    return _row(
        conn.execute(
            "SELECT * FROM merchant_category WHERE canonical_key = ?",
            (canonical_key,),
        ).fetchone()
    )


def put_merchant_decision(
    conn: sqlite3.Connection,
    *,
    canonical_key: str,
    display_name: str,
    category_id: int | None,
    source: str = "llm",
    confidence: float | None = None,
) -> None:
    """Record a merchant decision.

    A ``user`` decision is never overwritten by an automatic one — that is the
    guarantee that makes a manual correction permanent. Anything else upserts.
    """
    conn.execute(
        "INSERT INTO merchant_category "
        "(canonical_key, display_name, category_id, source, confidence, decided_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(canonical_key) DO UPDATE SET "
        "  display_name = excluded.display_name, "
        "  category_id  = excluded.category_id, "
        "  source       = excluded.source, "
        "  confidence   = excluded.confidence, "
        "  decided_at   = excluded.decided_at "
        "WHERE merchant_category.source != 'user' OR excluded.source = 'user'",
        (canonical_key, display_name, category_id, source, confidence),
    )


def apply_category_to_key(
    conn: sqlite3.Connection, canonical_key: str, category_id: int
) -> int:
    """Apply a category to every transaction sharing a canonical merchant.

    Broader than the old raw-descriptor propagation on purpose: correcting one
    "AMAZON KIDS *B26ME6RT2" row now fixes every Amazon Kids row, not just the
    ones with that exact reference id.
    """
    cur = conn.execute(
        "UPDATE transactions SET category_id = ?, resolution = 'override' "
        "WHERE canonical_key = ?",
        (category_id, canonical_key),
    )
    return cur.rowcount


def set_canonical_key(
    conn: sqlite3.Connection, tx_id: int, canonical_key: str
) -> None:
    conn.execute(
        "UPDATE transactions SET canonical_key = ? WHERE id = ?",
        (canonical_key, tx_id),
    )


def merchant_decision_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Decisions grouped by source — the "how much did we avoid asking" metric."""
    rows = conn.execute(
        "SELECT source, COUNT(*) AS n FROM merchant_category GROUP BY source"
    ).fetchall()
    return {r["source"]: int(r["n"]) for r in rows}


# --------------------------------------------------------------------------- #
# Merchant LLM cache (legacy, raw-descriptor keyed — read for migration only)
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


_TX_SORT_COLUMNS = {"date": "t.date", "amount": "t.amount", "id": "t.id"}


def _tx_filters(
    q: str | None, date_from: str | None, date_to: str | None
) -> tuple[str, list[Any]]:
    """Build the shared WHERE clause for transaction search/count."""
    clauses: list[str] = []
    params: list[Any] = []
    if q:
        like = f"%{q}%"
        clauses.append(
            "(t.raw_description LIKE ? OR t.clean_merchant LIKE ? "
            "OR c.name LIKE ? OR t.note LIKE ? OR t.tags LIKE ?)"
        )
        params += [like, like, like, like, like]
    if date_from:
        clauses.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("t.date <= ?")
        params.append(date_to)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def list_transactions(
    conn: sqlite3.Connection,
    limit: int = 100,
    offset: int = 0,
    q: str | None = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    where, params = _tx_filters(q, date_from, date_to)
    col = _TX_SORT_COLUMNS.get(sort_by, "t.date")
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    return _rows(
        conn.execute(
            "SELECT t.*, c.name AS category_name, c.color AS category_color "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            f"{where} ORDER BY {col} {direction}, t.id {direction} "
            "LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    )


def count_transactions(
    conn: sqlite3.Connection,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    where, params = _tx_filters(q, date_from, date_to)
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM transactions t "
            f"LEFT JOIN categories c ON t.category_id = c.id {where}",
            params,
        ).fetchone()[0]
    )


def get_transaction(conn: sqlite3.Connection, tx_id: int) -> dict[str, Any] | None:
    return _row(
        conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    )


TX_EDITABLE_FIELDS = {
    "date",
    "raw_description",
    "amount",
    "account_name",
    "category_id",
    "clean_merchant",
    "resolution",
    "note",
    "tags",
}


def update_transaction_fields(
    conn: sqlite3.Connection, tx_id: int, fields: dict[str, Any]
) -> None:
    """Update an arbitrary subset of a transaction's editable fields."""
    updates = {k: v for k, v in fields.items() if k in TX_EDITABLE_FIELDS}
    if not updates:
        return
    assignments = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE transactions SET {assignments} WHERE id = ?",
        (*updates.values(), tx_id),
    )


def delete_transaction(conn: sqlite3.Connection, tx_id: int) -> bool:
    # Children of a split are removed with their parent (ON DELETE CASCADE
    # requires foreign_keys pragma; delete explicitly to be safe).
    conn.execute("DELETE FROM transactions WHERE parent_tx_id = ?", (tx_id,))
    cur = conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Split transactions
# --------------------------------------------------------------------------- #
def split_transaction(
    conn: sqlite3.Connection,
    parent: dict[str, Any],
    splits: list[dict[str, Any]],
) -> list[int]:
    """Split a transaction into parts (e.g. one Costco run → two categories).

    The parent row is kept (its import_hash still blocks re-import duplicates)
    but flagged so aggregations skip it; the children carry the amounts.
    """
    child_ids: list[int] = []
    for part in splits:
        cur = conn.execute(
            "INSERT INTO transactions "
            "(date, raw_description, amount, account_name, category_id, "
            " clean_merchant, resolution, import_hash, parent_tx_id, note) "
            "VALUES (?, ?, ?, ?, ?, ?, 'split', NULL, ?, ?)",
            (
                parent["date"],
                parent["raw_description"],
                part["amount"],
                parent["account_name"],
                part.get("category_id"),
                parent.get("clean_merchant") or parent["raw_description"],
                parent["id"],
                part.get("note"),
            ),
        )
        child_ids.append(int(cur.lastrowid))
    conn.execute(
        "UPDATE transactions SET is_split_parent = 1 WHERE id = ?",
        (parent["id"],),
    )
    return child_ids


def unsplit_transaction(conn: sqlite3.Connection, parent_id: int) -> int:
    """Remove a split: delete children, restore the parent to a normal row."""
    cur = conn.execute(
        "DELETE FROM transactions WHERE parent_tx_id = ?", (parent_id,)
    )
    conn.execute(
        "UPDATE transactions SET is_split_parent = 0 WHERE id = ?", (parent_id,)
    )
    return cur.rowcount


# --------------------------------------------------------------------------- #
# Category management
# --------------------------------------------------------------------------- #
def update_category(
    conn: sqlite3.Connection,
    category_id: int,
    name: str | None = None,
    color: str | None = None,
) -> None:
    if name is not None:
        conn.execute(
            "UPDATE categories SET name = ? WHERE id = ?", (name, category_id)
        )
    if color is not None:
        conn.execute(
            "UPDATE categories SET color = ? WHERE id = ?", (color, category_id)
        )


def merge_category(
    conn: sqlite3.Connection, source_id: int, target_id: int
) -> int:
    """Move everything from source category into target, then delete source.

    Re-points transactions AND cache rules so future imports follow the merge.
    Returns the number of transactions moved.
    """
    cur = conn.execute(
        "UPDATE transactions SET category_id = ? WHERE category_id = ?",
        (target_id, source_id),
    )
    conn.execute(
        "UPDATE merchant_llm_cache SET category_id = ? WHERE category_id = ?",
        (target_id, source_id),
    )
    conn.execute("DELETE FROM categories WHERE id = ?", (source_id,))
    return cur.rowcount


def delete_category(
    conn: sqlite3.Connection, category_id: int, fallback_id: int | None
) -> None:
    """Delete a category, re-pointing its transactions/cache to a fallback."""
    conn.execute(
        "UPDATE transactions SET category_id = ? WHERE category_id = ?",
        (fallback_id, category_id),
    )
    conn.execute(
        "UPDATE merchant_llm_cache SET category_id = ? WHERE category_id = ?",
        (fallback_id, category_id),
    )
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))


def list_uncategorized_transactions(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Transactions that never got a resolved category (e.g. imported offline).

    Newest first. Sync walks this list in order and commits per chunk, so the
    ordering decides what gets fixed first when there is a large backlog: recent
    activity is what the ledger shows by default and what the budget and
    insights views are computed from, so it earns the first API calls. It also
    means a run that is interrupted or stopped early still leaves the most
    useful end of the data resolved. ``id`` breaks ties so the order is stable
    across runs (dates alone are not unique).
    """
    return _rows(
        conn.execute(
            "SELECT * FROM transactions "
            "WHERE (resolution = 'uncategorized' OR resolution IS NULL) "
            "AND is_split_parent = 0 "
            "ORDER BY date DESC, id DESC"
        ).fetchall()
    )


def apply_categorization(
    conn: sqlite3.Connection,
    tx_id: int,
    category_id: int | None,
    clean_merchant: str,
    resolution: str,
    canonical_key: str | None = None,
) -> None:
    """Write a freshly-resolved categorization onto an existing transaction.

    Stores the canonical merchant key alongside it when known, so a later user
    override can propagate across every spelling of that merchant without
    re-normalizing the table.
    """
    if canonical_key:
        conn.execute(
            "UPDATE transactions SET category_id = ?, clean_merchant = ?, "
            "resolution = ?, canonical_key = ? WHERE id = ?",
            (category_id, clean_merchant, resolution, canonical_key, tx_id),
        )
        return
    conn.execute(
        "UPDATE transactions SET category_id = ?, clean_merchant = ?, "
        "resolution = ? WHERE id = ?",
        (category_id, clean_merchant, resolution, tx_id),
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


def set_category_budget(
    conn: sqlite3.Connection,
    category_id: int,
    monthly_budget: float | None,
    rollover: bool | None = None,
) -> None:
    """Set (or clear, with None) a category's monthly budget target."""
    conn.execute(
        "UPDATE categories SET monthly_budget = ? WHERE id = ?",
        (monthly_budget, category_id),
    )
    if rollover is not None:
        conn.execute(
            "UPDATE categories SET budget_rollover = ? WHERE id = ?",
            (1 if rollover else 0, category_id),
        )


def observed_months(conn: sqlite3.Connection) -> list[str]:
    """Sorted distinct YYYY-MM months present in the transaction history."""
    rows = conn.execute(
        "SELECT DISTINCT substr(date, 1, 7) AS ym FROM transactions "
        "WHERE is_split_parent = 0 AND date IS NOT NULL ORDER BY ym"
    ).fetchall()
    return [r["ym"] for r in rows if r["ym"]]


def monthly_series(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Per-month, per-category signed totals (split parents excluded)."""
    return _rows(
        conn.execute(
            "SELECT substr(t.date, 1, 7) AS ym, c.id AS category_id, "
            "c.name AS category_name, c.color AS category_color, "
            "SUM(t.amount) AS total, COUNT(t.id) AS n "
            "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.is_split_parent = 0 AND t.date IS NOT NULL "
            # Transfers move money between the user's own accounts; counting
            # them would double-count the spending they settle.
            "AND COALESCE(c.is_transfer, 0) = 0 "
            "GROUP BY ym, t.category_id ORDER BY ym"
        ).fetchall()
    )


def category_breakdown_for_month(
    conn: sqlite3.Connection, month: str
) -> list[dict[str, Any]]:
    """Per-category totals for a single YYYY-MM month, with budget settings."""
    return _rows(
        conn.execute(
            "SELECT c.id AS category_id, c.name AS category_name, "
            "c.color AS category_color, c.monthly_budget AS monthly_budget, "
            "c.budget_rollover AS budget_rollover, "
            "COALESCE(SUM(t.amount), 0) AS total, COUNT(t.id) AS n "
            "FROM categories c "
            "JOIN transactions t ON t.category_id = c.id "
            "WHERE t.is_split_parent = 0 AND substr(t.date, 1, 7) = ? "
            "AND COALESCE(c.is_transfer, 0) = 0 "
            "GROUP BY c.id ORDER BY SUM(t.amount) ASC",
            (month,),
        ).fetchall()
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
            "c.budget_rollover AS budget_rollover, "
            "COALESCE(SUM(t.amount), 0) AS total, COUNT(t.id) AS n "
            "FROM categories c "
            "JOIN transactions t ON t.category_id = c.id "
            "WHERE t.is_split_parent = 0 "
            "AND COALESCE(c.is_transfer, 0) = 0 "
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
    row["events"] = json.loads(row.get("events") or "[]")
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
    events: list[dict[str, Any]] | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO branches (name, is_base, parameters, milestones, events) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            name,
            1 if is_base else 0,
            json.dumps(parameters),
            json.dumps(milestones),
            json.dumps(events or []),
        ),
    )
    return int(cur.lastrowid)


def update_branch(
    conn: sqlite3.Connection,
    branch_id: int,
    name: str | None = None,
    parameters: dict[str, Any] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
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
    if events is not None:
        fields.append("events = ?")
        values.append(json.dumps(events))
    if not fields:
        return
    values.append(branch_id)
    conn.execute(f"UPDATE branches SET {', '.join(fields)} WHERE id = ?", values)


def delete_branch(conn: sqlite3.Connection, branch_id: int) -> None:
    conn.execute("DELETE FROM branches WHERE id = ? AND is_base = 0", (branch_id,))


# --------------------------------------------------------------------------- #
# Goals (target net worth / cash by a future month)
# --------------------------------------------------------------------------- #
def list_goals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, label, kind, target_amount, target_month FROM goals "
        "ORDER BY target_month ASC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def create_goal(
    conn: sqlite3.Connection,
    label: str,
    kind: str,
    target_amount: float,
    target_month: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO goals (label, kind, target_amount, target_month) "
        "VALUES (?, ?, ?, ?)",
        (label, kind, target_amount, target_month),
    )
    return int(cur.lastrowid)


def get_goal(conn: sqlite3.Connection, goal_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, label, kind, target_amount, target_month FROM goals WHERE id = ?",
        (goal_id,),
    ).fetchone()
    return dict(row) if row else None


def update_goal(conn: sqlite3.Connection, goal_id: int, **fields: Any) -> None:
    cols = [k for k, v in fields.items() if v is not None]
    if not cols:
        return
    assignments = ", ".join(f"{c} = ?" for c in cols)
    values = [fields[c] for c in cols]
    values.append(goal_id)
    conn.execute(f"UPDATE goals SET {assignments} WHERE id = ?", values)


def delete_goal(conn: sqlite3.Connection, goal_id: int) -> None:
    conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))


# --------------------------------------------------------------------------- #
# Reset (clear the user's financial data back to an empty slate)
# --------------------------------------------------------------------------- #
def reset_financial_data(conn: sqlite3.Connection, base_parameters: dict) -> None:
    """Wipe transactions, cache, budgets, and sandbox branches; reset the base.

    Keeps categories (names/colors) and app settings (LLM provider + keys).
    The Base Plan is reset to the supplied empty parameters with no milestones.
    """
    conn.execute("DELETE FROM transactions")
    conn.execute("DELETE FROM merchant_llm_cache")
    conn.execute("DELETE FROM branches WHERE is_base = 0")
    conn.execute("UPDATE categories SET monthly_budget = NULL")
    conn.execute(
        "UPDATE branches SET parameters = ?, milestones = '[]' WHERE is_base = 1",
        (json.dumps(base_parameters),),
    )


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
