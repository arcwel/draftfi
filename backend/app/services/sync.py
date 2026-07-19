"""Sync: reprocess data that couldn't be resolved before, with live progress.

The headline job is re-categorizing transactions that came in as
"Uncategorized" — typically because they were imported while no LLM was
reachable. Running sync after connecting a provider (or after the cache learned
a rule from a manual override) resolves them through the same cache-first
pipeline used on import.

Sync runs as a background job so a large batch reports incremental progress
(processed / total) that the frontend polls, rather than blocking one request.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass

from app.db import repository as repo
from app.db.connection import session
from app.services import categorization, llm, llm_config
from app.services.csv_parser import ParsedRow


@dataclass
class SyncJob:
    job_id: str
    state: str = "pending"  # pending | running | done | error
    total: int = 0
    processed: int = 0
    recategorized: int = 0
    cache_hits: int = 0
    llm_cleaned: int = 0
    still_uncategorized: int = 0
    llm_available: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# job_id -> SyncJob. In-memory (local-first, single user).
_JOBS: dict[str, SyncJob] = {}


def new_job(job_id: str) -> SyncJob:
    job = SyncJob(job_id=job_id)
    _JOBS[job_id] = job
    return job


def get_job(job_id: str) -> SyncJob | None:
    return _JOBS.get(job_id)


async def _run(conn: sqlite3.Connection, job: SyncJob) -> None:
    """Categorize every unresolved row, updating the job as it goes."""
    config = llm_config.resolve_config(conn)
    available, _, _ = await llm.health(config)
    job.llm_available = available
    category_names = [c["name"] for c in repo.list_categories(conn)]

    rows = repo.list_uncategorized_transactions(conn)
    job.total = len(rows)

    for tx in rows:
        parsed = ParsedRow(
            date=tx["date"],
            raw_description=tx["raw_description"],
            amount=tx["amount"],
            account_name=tx["account_name"],
        )
        outcome = await categorization.categorize_row(
            conn, parsed, category_names, config, llm_available=available
        )
        if outcome.resolution in ("cache", "llm"):
            repo.apply_categorization(
                conn,
                int(tx["id"]),
                outcome.category_id,
                outcome.clean_merchant,
                outcome.resolution,
            )
            job.recategorized += 1
            if outcome.resolution == "cache":
                job.cache_hits += 1
            else:
                job.llm_cleaned += 1
                category_names = [c["name"] for c in repo.list_categories(conn)]
        else:
            job.still_uncategorized += 1
        job.processed += 1
        # Commit periodically so progress is durable and status reads see it.
        if job.processed % 20 == 0:
            conn.commit()

    conn.commit()


async def run_sync_job(job_id: str) -> None:
    """Background entry point: opens its own connection and runs the sync."""
    job = _JOBS[job_id]
    job.state = "running"
    try:
        with session() as conn:
            await _run(conn, job)
        job.state = "done"
    except Exception as exc:  # pragma: no cover - defensive
        job.state = "error"
        job.error = str(exc)


async def resync(conn: sqlite3.Connection) -> SyncJob:
    """Synchronous helper (used by tests): run the sync on a given connection."""
    job = SyncJob(job_id="inline")
    job.state = "running"
    await _run(conn, job)
    job.state = "done"
    return job
