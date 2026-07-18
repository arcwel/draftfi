"""Budget endpoints: monthly spending by category + scenario impact."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import repository as repo
from app.db.connection import get_db
from app.models.schemas import (
    BudgetOverride,
    BudgetRequest,
    BudgetSummary,
    Category,
)
from app.services import budget

router = APIRouter(tags=["budget"])


@router.post("/budget", response_model=BudgetSummary)
def get_budget(
    body: BudgetRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> BudgetSummary:
    """Monthly budget from history, with the active scenario's impact applied."""
    return budget.compute_budget(conn, body.parameters, body.milestones)


@router.patch("/categories/{category_id}/budget", response_model=Category)
def set_budget(
    category_id: int,
    body: BudgetOverride,
    conn: sqlite3.Connection = Depends(get_db),
) -> Category:
    """Set or clear a category's monthly budget target."""
    category = repo.get_category(conn, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    amount = body.monthly_budget
    if amount is not None and amount < 0:
        raise HTTPException(status_code=400, detail="Budget must be non-negative.")
    repo.set_category_budget(conn, category_id, amount)
    conn.commit()
    updated = repo.get_category(conn, category_id)
    assert updated is not None
    return Category(**updated)
