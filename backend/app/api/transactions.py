"""Transaction listing, manual CRUD, splits, and category endpoints."""
from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.db import repository as repo
from app.db.connection import get_db
from app.models.schemas import (
    Category,
    CategoryCreate,
    CategoryMerge,
    CategoryOverride,
    CategoryUpdate,
    SplitRequest,
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
    q: str | None = Query(None, max_length=200),
    sort_by: str = Query("date", pattern="^(date|amount|id)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    date_from: str | None = Query(None, max_length=10),
    date_to: str | None = Query(None, max_length=10),
    conn: sqlite3.Connection = Depends(get_db),
) -> TransactionPage:
    """Server-side search / sort / pagination over the full ledger."""
    items = repo.list_transactions(
        conn,
        limit=limit,
        offset=offset,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        date_from=date_from,
        date_to=date_to,
    )
    total = repo.count_transactions(conn, q=q, date_from=date_from, date_to=date_to)
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
    assert tx_id is not None
    if body.note or body.tags:
        repo.update_transaction_fields(
            conn,
            tx_id,
            {"note": body.note, "tags": json.dumps(body.tags) if body.tags else None},
        )
    conn.commit()
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
    if "tags" in fields:
        fields["tags"] = json.dumps(fields["tags"]) if fields["tags"] else None
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


# --------------------------------------------------------------------------- #
# Split transactions
# --------------------------------------------------------------------------- #
@router.post("/transactions/{tx_id}/split", response_model=list[Transaction])
def split_transaction(
    tx_id: int,
    body: SplitRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Transaction]:
    """Split one transaction across categories (amounts must sum to it)."""
    tx = repo.get_transaction(conn, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if tx.get("is_split_parent"):
        raise HTTPException(status_code=400, detail="Already split — unsplit first.")
    if tx.get("parent_tx_id"):
        raise HTTPException(status_code=400, detail="Cannot split a split part.")

    total = sum(p.amount for p in body.splits)
    if abs(total - tx["amount"]) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Split amounts must sum to {tx['amount']:.2f} (got {total:.2f}).",
        )
    for part in body.splits:
        if part.category_id is not None:
            if repo.get_category(conn, part.category_id) is None:
                raise HTTPException(status_code=400, detail="Unknown category id.")

    child_ids = repo.split_transaction(
        conn, tx, [p.model_dump() for p in body.splits]
    )
    conn.commit()
    return [_tx_with_category(conn, cid) for cid in child_ids]


@router.post("/transactions/{tx_id}/unsplit", response_model=Transaction)
def unsplit_transaction(
    tx_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> Transaction:
    """Undo a split: remove the parts, restore the original row."""
    tx = repo.get_transaction(conn, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if not tx.get("is_split_parent"):
        raise HTTPException(status_code=400, detail="Transaction is not split.")
    repo.unsplit_transaction(conn, tx_id)
    conn.commit()
    return _tx_with_category(conn, tx_id)


# --------------------------------------------------------------------------- #
# Category management
# --------------------------------------------------------------------------- #
def _protected_category(conn: sqlite3.Connection, category_id: int) -> bool:
    cat = repo.get_category(conn, category_id)
    return cat is not None and cat["name"] == "Uncategorized"


@router.post("/categories", response_model=Category, status_code=201)
def create_category(
    body: CategoryCreate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Category:
    if repo.get_category_by_name(conn, body.name.strip()):
        raise HTTPException(status_code=409, detail="Category already exists.")
    cat_id = repo.upsert_category(conn, body.name.strip(), body.color)
    conn.commit()
    created = repo.get_category(conn, cat_id)
    assert created is not None
    return Category(**created)


@router.patch("/categories/{category_id}", response_model=Category)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Category:
    if repo.get_category(conn, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    name = body.name.strip() if body.name else None
    if name:
        existing = repo.get_category_by_name(conn, name)
        if existing and existing["id"] != category_id:
            raise HTTPException(status_code=409, detail="Name already in use.")
    repo.update_category(conn, category_id, name=name, color=body.color)
    conn.commit()
    updated = repo.get_category(conn, category_id)
    assert updated is not None
    return Category(**updated)


@router.delete("/categories/{category_id}", status_code=204, response_class=Response)
def delete_category(
    category_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Delete a category; its transactions move to Uncategorized."""
    if repo.get_category(conn, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    if _protected_category(conn, category_id):
        raise HTTPException(status_code=403, detail="Uncategorized is protected.")
    fallback = repo.get_category_by_name(conn, "Uncategorized")
    repo.delete_category(conn, category_id, fallback["id"] if fallback else None)
    conn.commit()
    return Response(status_code=204)


@router.post("/categories/{category_id}/merge", response_model=Category)
def merge_category(
    category_id: int,
    body: CategoryMerge,
    conn: sqlite3.Connection = Depends(get_db),
) -> Category:
    """Merge this category into another (re-points transactions + cache rules)."""
    if category_id == body.target_id:
        raise HTTPException(status_code=400, detail="Cannot merge into itself.")
    source = repo.get_category(conn, category_id)
    target = repo.get_category(conn, body.target_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    if _protected_category(conn, category_id):
        raise HTTPException(status_code=403, detail="Uncategorized is protected.")
    repo.merge_category(conn, category_id, body.target_id)
    conn.commit()
    return Category(**repo.get_category(conn, body.target_id))
