"""Budget endpoints: monthly spending, scenario impact, and trends."""
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
    TrendsSummary,
)
from app.services import budget

router = APIRouter(tags=["budget"])


@router.post("/budget", response_model=BudgetSummary)
def get_budget(
    body: BudgetRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> BudgetSummary:
    """Monthly budget from history (all-time average or a single month)."""
    return budget.compute_budget(
        conn, body.parameters, body.milestones, month=body.month
    )


@router.get("/budget/trends", response_model=TrendsSummary)
def get_trends(conn: sqlite3.Connection = Depends(get_db)) -> TrendsSummary:
    """Month-over-month cash flow and per-category series for trend charts."""
    return budget.compute_trends(conn)


@router.patch("/categories/{category_id}/budget", response_model=Category)
def set_budget(
    category_id: int,
    body: BudgetOverride,
    conn: sqlite3.Connection = Depends(get_db),
) -> Category:
    """Set/clear a category's monthly budget target and rollover flag."""
    category = repo.get_category(conn, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    amount = body.monthly_budget
    if amount is not None and amount < 0:
        raise HTTPException(status_code=400, detail="Budget must be non-negative.")
    repo.set_category_budget(conn, category_id, amount, rollover=body.rollover)
    conn.commit()
    updated = repo.get_category(conn, category_id)
    assert updated is not None
    return Category(**updated)
