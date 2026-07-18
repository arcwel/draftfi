"""CSV import + processing-status endpoints."""
from __future__ import annotations

import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.db.connection import get_db
from app.models.schemas import ImportResult
from app.services import ingestion

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/csv", response_model=ImportResult)
async def import_csv(
    file: UploadFile = File(...),
    account_name: str = Form("Imported Account"),
    conn: sqlite3.Connection = Depends(get_db),
) -> ImportResult:
    """Upload a bank CSV; parse, categorize, and persist it synchronously."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    job = ingestion.new_job(uuid.uuid4().hex)
    status = await ingestion.run_import(conn, content, account_name, job)
    return ImportResult(
        imported=status.imported,
        skipped_duplicates=status.skipped_duplicates,
        skipped_invalid=status.skipped_invalid,
        cache_hits=status.cache_hits,
        llm_cleaned=status.llm_cleaned,
        uncategorized=status.uncategorized,
        errors=status.errors,
    )


@router.get("/status/{job_id}")
def import_status(job_id: str) -> dict:
    """Poll live progress of an import job for the frontend spinner."""
    job = ingestion.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job.to_dict()
