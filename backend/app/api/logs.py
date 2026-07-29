"""Diagnostics: let the user hand over their logs without a terminal.

The point of this endpoint is that a bug report should cost one click. Logs are
bundled into a single zip (current file plus rotated siblings) so there is one
thing to attach, and credentials are already stripped on write by
``logging_setup.RedactFilter``.
"""
from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import LogsInfo
from app.services import logging_setup

router = APIRouter(prefix="/logs", tags=["diagnostics"])


@router.get("", response_model=LogsInfo)
def logs_info() -> LogsInfo:
    """Where the logs live and how big they are, for the settings panel."""
    files = logging_setup.log_files()
    return LogsInfo(
        path=str(logging_setup.log_path()),
        directory=str(logging_setup.log_dir()),
        files=len(files),
        size_bytes=sum(f.stat().st_size for f in files if f.exists()),
    )


@router.get("/export")
def export_logs() -> StreamingResponse:
    """Download every log file as one zip."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        wrote_any = False
        for path in logging_setup.log_files():
            try:
                archive.write(path, arcname=path.name)
                wrote_any = True
            except OSError:  # pragma: no cover - file rotated mid-read
                continue
        if not wrote_any:
            archive.writestr(
                "README.txt",
                "No DraftFi log files were found yet.\n"
                f"Logs are written to: {logging_setup.log_dir()}\n",
            )
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="draftfi-logs.zip"'},
    )
