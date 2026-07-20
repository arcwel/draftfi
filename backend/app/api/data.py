"""Data-management endpoints (sync / reset)."""
from __future__ import annotations

import asyncio
import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.db import repository as repo
from app.db.connection import get_db
from app.db.schema import BASE_PLAN_PARAMETERS
from app.services import sync as sync_service

router = APIRouter(tags=["data"])

# Retain in-flight tasks (the loop only holds a weak ref) so a sync can't be
# garbage-collected mid-run and leave its job stuck without a terminal state.
_background_tasks: set[asyncio.Task] = set()


@router.post("/sync")
async def sync() -> dict:
    """Start a background re-categorization of 'Uncategorized' transactions.

    Returns a job id immediately; poll ``/sync/status/{job_id}`` for live
    progress (processed / total) so large batches show real movement.
    """
    job = sync_service.new_job(uuid.uuid4().hex)
    task = asyncio.create_task(sync_service.run_sync_job(job.job_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"job_id": job.job_id}


@router.get("/sync/status/{job_id}")
def sync_status(job_id: str) -> dict:
    job = sync_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown sync job.")
    return job.to_dict()


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
