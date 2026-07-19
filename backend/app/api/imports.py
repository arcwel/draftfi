"""CSV import + processing-status endpoints."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services import ingestion

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/csv")
async def import_csv(
    file: UploadFile = File(...),
    account_name: str = Form("Imported Account"),
) -> dict:
    """Upload a bank CSV; parse + categorize it in the background.

    Returns a job id immediately. Poll ``/import/status/{job_id}`` for live
    progress (processed / total) — large statements report real movement rather
    than blocking one long request.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    job = ingestion.new_job(uuid.uuid4().hex)
    asyncio.create_task(
        ingestion.run_import_job(job.job_id, content, account_name)
    )
    return {"job_id": job.job_id}


@router.get("/status/{job_id}")
def import_status(job_id: str) -> dict:
    """Poll live progress of an import job for the frontend spinner."""
    job = ingestion.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job.to_dict()
