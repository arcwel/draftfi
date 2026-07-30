"""Merchant review: categorize once, apply to every transaction.

The ledger corrects one transaction at a time, which does not scale — a real
file had 3,887 unresolved transactions across 1,242 merchants. But merchant
frequency is heavily skewed: on that same file the top 25 merchants covered
1,169 transactions and the top 100 covered 2,151, while 810 merchants appeared
exactly once. So the leverage is entirely in deciding per *merchant*, ranked by
how many transactions each one settles.

This is the surface for that. It hands back the unresolved merchants worst-first
with whatever the model already suggested, and takes back a batch of confirmed
decisions. Each decision is stored as ``source='user'``, which outranks every
automatic pass permanently, and is applied to that merchant's whole history.
"""
from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import repository as repo
from app.db.connection import get_db
from app.models.schemas import (
    MerchantDecisionRequest,
    MerchantDecisionResult,
    MerchantReviewPage,
    MerchantReviewRow,
)
from app.services import descriptors

log = logging.getLogger("draftfi.api.merchants")

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.get("/review", response_model=MerchantReviewPage)
def review_queue(
    limit: int = 200,
    offset: int = 0,
    conn: sqlite3.Connection = Depends(get_db),
) -> MerchantReviewPage:
    """Unresolved merchants, most transactions first.

    Ordering is the whole point: working this list top-down means the first
    handful of decisions clear hundreds of rows.
    """
    limit = max(1, min(limit, 500))
    rows = repo.merchants_needing_review(conn, limit=limit, offset=offset)
    totals = repo.review_queue_totals(conn)
    items = []
    for row in rows:
        row = dict(row)
        # Prefer a stored name, else derive one from the key. Never fall back to
        # clean_merchant: pre-normalizer rows hold the whole raw descriptor there.
        row["display_name"] = row.pop("stored_display_name", None) or (
            descriptors.display_name(row["canonical_key"])
        )
        items.append(MerchantReviewRow(**row))
    return MerchantReviewPage(
        items=items,
        total_merchants=totals["merchants"],
        total_transactions=totals["transactions"],
    )


@router.post("/decisions", response_model=MerchantDecisionResult)
def save_decisions(
    body: MerchantDecisionRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> MerchantDecisionResult:
    """Confirm a batch of merchant→category decisions.

    Applied in one transaction so a partial save can't leave the memo table and
    the ledger disagreeing about what a merchant is.
    """
    if not body.decisions:
        return MerchantDecisionResult(merchants=0, transactions=0)

    known = {int(c["id"]) for c in repo.list_categories(conn)}
    unknown = {d.category_id for d in body.decisions} - known
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown category ids: {sorted(unknown)}"
        )

    merchants = 0
    transactions = 0
    for decision in body.decisions:
        key = decision.canonical_key.strip()
        if not key:
            continue
        repo.put_merchant_decision(
            conn,
            canonical_key=key,
            display_name=decision.display_name or key,
            category_id=decision.category_id,
            source="user",
            confidence=1.0,
        )
        transactions += repo.apply_category_to_key(conn, key, decision.category_id)
        merchants += 1
    conn.commit()
    log.info(
        "Merchant review: %d decisions applied to %d transactions",
        merchants,
        transactions,
    )
    return MerchantDecisionResult(merchants=merchants, transactions=transactions)
