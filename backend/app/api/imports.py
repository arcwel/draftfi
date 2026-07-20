"""Statement import (CSV/OFX/QFX/QIF) + processing-status endpoints."""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services import ingestion

router = APIRouter(prefix="/import", tags=["import"])

ALLOWED_EXT = (".csv", ".ofx", ".qfx", ".qif")

# Hold strong references to in-flight background tasks — the event loop only
# keeps a weak reference, so an un-retained task can be GC'd mid-import.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.post("/csv")
async def import_files(
    files: list[UploadFile] = File(...),
    account_name: str = Form("Imported Account"),
    mapping: str | None = Form(None),
) -> dict:
    """Upload one or more bank statements; parse + categorize in the background.

    Accepts CSV/OFX/QFX/QIF. ``mapping`` (JSON of canonical-field → header) is
    used when a CSV needs manual column mapping. Returns a job id; poll
    ``/import/status/{job_id}`` for live progress and any ``needs_mapping``
    prompt.
    """
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "upload"
        if not name.lower().endswith(ALLOWED_EXT):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file '{name}'. Use CSV, OFX, QFX, or QIF.",
            )
        content = await f.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"'{name}' is empty.")
        payloads.append((name, content))

    parsed_mapping = None
    if mapping:
        try:
            parsed_mapping = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid mapping JSON."
            ) from exc

    job = ingestion.new_job(uuid.uuid4().hex)
    _spawn(
        ingestion.run_import_job(job.job_id, payloads, account_name, parsed_mapping)
    )
    return {"job_id": job.job_id}


@router.get("/status/{job_id}")
def import_status(job_id: str) -> dict:
    """Poll live progress of an import job for the frontend."""
    job = ingestion.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job.to_dict()
