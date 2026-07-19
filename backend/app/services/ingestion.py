"""Import orchestration: parse -> categorize -> persist, with live status.

A tiny in-process job registry backs the frontend processing spinner (PRD 4.1).
Because DraftFi is single-user local-first, an in-memory dict is sufficient and
avoids extra infrastructure.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field

from app.db import repository as repo
from app.db.connection import session
from app.services import categorization, llm, llm_config
from app.services.csv_parser import parse_csv


@dataclass
class JobStatus:
    job_id: str
    state: str = "pending"  # pending | parsing | categorizing | done | error
    total: int = 0
    processed: int = 0
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_invalid: int = 0
    cache_hits: int = 0
    llm_cleaned: int = 0
    uncategorized: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# job_id -> JobStatus. Cleared on process restart (acceptable for local-first).
_JOBS: dict[str, JobStatus] = {}


def new_job(job_id: str) -> JobStatus:
    status = JobStatus(job_id=job_id)
    _JOBS[job_id] = status
    return status


def get_job(job_id: str) -> JobStatus | None:
    return _JOBS.get(job_id)


async def run_import(
    conn: sqlite3.Connection,
    content: bytes,
    account_hint: str,
    status: JobStatus,
) -> JobStatus:
    """Full import pipeline. Mutates and returns ``status`` as it progresses."""
    status.state = "parsing"
    report = parse_csv(content, default_account=account_hint or "Imported Account")
    status.errors.extend(report.errors)
    status.skipped_invalid = len(report.errors)
    status.total = len(report.rows)

    status.state = "categorizing"
    config = llm_config.resolve_config(conn)
    available, _, _ = await llm.health(config)
    category_names = [c["name"] for c in repo.list_categories(conn)]

    # Additive, non-destructive: rows already present are left exactly as they
    # are (including manual category overrides). Skip them BEFORE any LLM work
    # so re-imports are cheap and never mutate existing data.
    pending: list = []
    for row in report.rows:
        if repo.transaction_exists(conn, row.import_hash):
            status.processed += 1
            status.skipped_duplicates += 1
        else:
            pending.append(row)

    # Categorize in chunks: one LLM call per chunk instead of one per row.
    CHUNK = 25
    for start in range(0, len(pending), CHUNK):
        chunk = pending[start : start + CHUNK]
        outcomes = await categorization.categorize_rows_batch(
            conn, chunk, category_names, config, llm_available=available
        )
        for row, result in zip(chunk, outcomes, strict=False):
            tx_id = repo.insert_transaction(
                conn,
                {
                    "date": row.date,
                    "raw_description": row.raw_description,
                    "amount": row.amount,
                    "account_name": row.account_name,
                    "category_id": result.category_id,
                    "clean_merchant": result.clean_merchant,
                    "resolution": result.resolution,
                    "import_hash": row.import_hash,
                },
            )
            status.processed += 1
            if tx_id is None:
                # Lost a race / exact-hash collision — counts as unchanged.
                status.skipped_duplicates += 1
                continue
            status.imported += 1
            if result.resolution == "cache":
                status.cache_hits += 1
            elif result.resolution == "llm":
                status.llm_cleaned += 1
            else:
                status.uncategorized += 1
        # New categories may have been created by the model this chunk.
        category_names = [c["name"] for c in repo.list_categories(conn)]
        # Commit per chunk so progress is durable and status polls see it.
        conn.commit()

    conn.commit()
    status.state = "done"
    return status


async def run_import_job(job_id: str, content: bytes, account_hint: str) -> None:
    """Background entry point: opens its own connection and runs the import."""
    job = _JOBS.get(job_id)
    if job is None:
        return
    try:
        with session() as conn:
            await run_import(conn, content, account_hint, job)
    except Exception as exc:  # pragma: no cover - defensive
        job.state = "error"
        job.errors.append(str(exc))
