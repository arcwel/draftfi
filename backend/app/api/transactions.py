"""Transaction listing + category-override endpoints (PRD 4.3, 6.1)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import repository as repo
from app.db.connection import get_db
from app.models.schemas import (
    Category,
    CategoryOverride,
    Transaction,
    TransactionPage,
)

router = APIRouter(tags=["transactions"])


@router.get("/categories", response_model=list[Category])
def get_categories(conn: sqlite3.Connection = Depends(get_db)) -> list[Category]:
    return [Category(**c) for c in repo.list_categories(conn)]


@router.get("/transactions", response_model=TransactionPage)
def get_transactions(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> TransactionPage:
    items = repo.list_transactions(conn, limit=limit, offset=offset)
    total = repo.count_transactions(conn)
    return TransactionPage(
        items=[Transaction(**t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/transactions/{tx_id}/category", response_model=Transaction)
def override_category(
    tx_id: int,
    body: CategoryOverride,
    conn: sqlite3.Connection = Depends(get_db),
) -> Transaction:
    """Override a transaction's category and sync the rule globally.

    Updates the cache mapping for the raw descriptor and re-tags every past &
    future transaction with the same raw string (PRD 6.1 User Override Sync).
    """
    tx = repo.get_transaction(conn, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    category = repo.get_category(conn, body.category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="Unknown category id.")

    raw = tx["raw_description"]
    clean = tx.get("clean_merchant") or raw
    # Cache write mirrors the choice for all future imports of this raw string.
    repo.put_cache(conn, raw, clean, body.category_id)
    # Propagate to all existing rows sharing the descriptor.
    repo.apply_category_to_raw(conn, raw, body.category_id)
    conn.commit()

    updated = repo.get_transaction(conn, tx_id)
    assert updated is not None
    return Transaction(
        **updated,
        category_name=category["name"],
        category_color=category["color"],
    )
