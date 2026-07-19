"""Data-management endpoints (reset / clear)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.db import repository as repo
from app.db.connection import get_db
from app.db.schema import BASE_PLAN_PARAMETERS

router = APIRouter(tags=["data"])


@router.post("/reset")
def reset_data(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Clear all financial data and return to an empty slate.

    Deletes every transaction, the merchant cache, all sandbox branches, and any
    budget targets, and resets the Base Plan to empty values. Categories and LLM
    settings (including saved API keys) are preserved.
    """
    repo.reset_financial_data(conn, BASE_PLAN_PARAMETERS)
    conn.commit()
    return {"status": "reset", "transactions": 0}
