"""Transaction listing, manual CRUD, and category-override endpoints."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.db import repository as repo
from app.db.connection import get_db
from app.models.schemas import (
    Category,
    CategoryOverride,
    Transaction,
    TransactionCreate,
    TransactionPage,
    TransactionUpdate,
)

router = APIRouter(tags=["transactions"])


def _tx_with_category(conn: sqlite3.Connection, tx_id: int) -> Transaction:
    tx = repo.get_transaction(conn, tx_id)
    assert tx is not None
    category = repo.get_category(conn, tx["category_id"]) if tx["category_id"] else None
    return Transaction(
        **tx,
        category_name=category["name"] if category else None,
        category_color=category["color"] if category else None,
    )


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


@router.post("/transactions", response_model=Transaction, status_code=201)
def create_transaction(
    body: TransactionCreate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Transaction:
    """Manually add a transaction (cash spending, missing rows, corrections)."""
    if body.category_id is not None:
        if repo.get_category(conn, body.category_id) is None:
            raise HTTPException(status_code=400, detail="Unknown category id.")
    category_id = body.category_id
    if category_id is None:
        uncat = repo.get_category_by_name(conn, "Uncategorized")
        category_id = uncat["id"] if uncat else None
    tx_id = repo.insert_transaction(
        conn,
        {
            "date": body.date,
            "raw_description": body.raw_description,
            "amount": body.amount,
            "account_name": body.account_name or "Manual Entry",
            "category_id": category_id,
            "clean_merchant": body.clean_merchant or body.raw_description,
            "resolution": "manual",
            # NULL import_hash: manual entries never collide with imports, and
            # two identical cash purchases are both legitimate.
            "import_hash": None,
        },
    )
    conn.commit()
    assert tx_id is not None
    return _tx_with_category(conn, tx_id)


@router.patch("/transactions/{tx_id}", response_model=Transaction)
def update_transaction(
    tx_id: int,
    body: TransactionUpdate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Transaction:
    """Edit a transaction's fields (fix a mis-parsed amount, date, etc.)."""
    if repo.get_transaction(conn, tx_id) is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    fields = body.model_dump(exclude_unset=True)
    if "category_id" in fields and fields["category_id"] is not None:
        if repo.get_category(conn, fields["category_id"]) is None:
            raise HTTPException(status_code=400, detail="Unknown category id.")
    if "raw_description" in fields and not (fields["raw_description"] or "").strip():
        raise HTTPException(status_code=400, detail="Description cannot be empty.")
    repo.update_transaction_fields(conn, tx_id, fields)
    conn.commit()
    return _tx_with_category(conn, tx_id)


@router.delete("/transactions/{tx_id}", status_code=204, response_class=Response)
def delete_transaction(
    tx_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    if not repo.delete_transaction(conn, tx_id):
        raise HTTPException(status_code=404, detail="Transaction not found.")
    conn.commit()
    return Response(status_code=204)


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
