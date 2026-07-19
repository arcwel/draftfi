"""Data portability: export, backup, and restore.

Local-first means the user can always get their data OUT: transactions as CSV,
a full JSON dump, and raw database backup/restore.
"""
from __future__ import annotations

import csv
import io
import shutil
import sqlite3
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.config import get_settings
from app.db import repository as repo
from app.db.connection import get_db

router = APIRouter(prefix="/export", tags=["export"])

REQUIRED_TABLES = {"categories", "merchant_llm_cache", "transactions", "branches"}


@router.get("/transactions.csv")
def export_transactions_csv(conn: sqlite3.Connection = Depends(get_db)):
    """Download every transaction as a CSV."""
    rows = conn.execute(
        "SELECT t.date, t.raw_description, t.clean_merchant, t.amount, "
        "t.account_name, c.name AS category, t.resolution "
        "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
        "ORDER BY t.date, t.id"
    ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["date", "raw_description", "clean_merchant", "amount", "account",
         "category", "resolution"]
    )
    for r in rows:
        writer.writerow([r["date"], r["raw_description"], r["clean_merchant"],
                         r["amount"], r["account_name"], r["category"],
                         r["resolution"]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=draftfi-transactions.csv"
        },
    )


@router.get("/data.json")
def export_data_json(conn: sqlite3.Connection = Depends(get_db)) -> JSONResponse:
    """Download the full dataset (transactions, categories, plans, budgets)."""
    payload = {
        "categories": repo.list_categories(conn),
        "transactions": [
            dict(r) for r in conn.execute(
                "SELECT * FROM transactions ORDER BY date, id"
            ).fetchall()
        ],
        "merchant_cache": [
            dict(r) for r in conn.execute(
                "SELECT * FROM merchant_llm_cache"
            ).fetchall()
        ],
        "branches": repo.list_branches(conn),
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": "attachment; filename=draftfi-data.json"},
    )


@router.get("/backup.db")
def download_backup(conn: sqlite3.Connection = Depends(get_db)) -> FileResponse:
    """Download the raw SQLite database (a complete backup)."""
    # Fold WAL contents into the main file so the download is self-contained.
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db_path = Path(get_settings().db_path)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found.")
    return FileResponse(
        db_path,
        media_type="application/octet-stream",
        filename="draftfi-backup.db",
    )


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...)) -> dict:
    """Replace the database with an uploaded DraftFi backup.

    The upload is validated as a DraftFi SQLite file before anything is
    touched, and the current database is kept alongside as ``.pre-restore``.
    """
    content = await file.read()
    if not content.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=400, detail="Not a SQLite database file.")

    # Validate in a temp file: must contain the DraftFi tables.
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        check = sqlite3.connect(tmp_path)
        try:
            tables = {
                r[0]
                for r in check.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing = REQUIRED_TABLES - tables
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not a DraftFi backup (missing tables: {sorted(missing)}).",
                )
            tx_count = check.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        finally:
            check.close()

        db_path = Path(get_settings().db_path)
        # Keep the current data recoverable, then swap in the backup.
        if db_path.exists():
            shutil.copy2(db_path, db_path.with_suffix(db_path.suffix + ".pre-restore"))
        for stale in (
            db_path.with_name(db_path.name + "-wal"),
            db_path.with_name(db_path.name + "-shm"),
        ):
            stale.unlink(missing_ok=True)
        shutil.copy2(tmp_path, db_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"status": "restored", "transactions": tx_count}
