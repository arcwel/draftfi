"""Sync: reprocess data that couldn't be resolved before, with live progress.

The headline job is re-categorizing transactions that came in as
"Uncategorized" — typically because they were imported while no LLM was
reachable. Running sync after connecting a provider (or after the cache learned
a rule from a manual override) resolves them through the same cache-first
pipeline used on import.

Sync runs as a background job so a large batch reports incremental progress
(processed / total) that the frontend polls, rather than blocking one request.

A long run is a hostile environment: across hundreds of provider calls a
transient 5xx is close to certain, and a model can be retired mid-run. Neither
should end the job. Transport blips are absorbed by the retry/backoff in
``services.llm``; a retired model is repaired in place by ``model_guard`` and
the affected chunk is replayed against the replacement.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass

from app.db import repository as repo
from app.db.connection import session
from app.services import categorization, llm_config, model_guard
from app.services.csv_parser import ParsedRow

log = logging.getLogger("draftfi.sync")


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
    # Why rows stayed uncategorized (e.g. the provider rate-limited us). Set
    # even on a "done" run so the UI never reports a silent no-op success.
    detail: str | None = None
    stopped_early: bool = False
    # Set when a retired model was swapped out mid-flight, so the UI can say so
    # instead of leaving the user wondering why the model name changed.
    model_switched: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# job_id -> SyncJob. In-memory (local-first, single user).
_JOBS: dict[str, SyncJob] = {}

# One LLM call per chunk (see categorize_rows_batch) instead of per row.
CHUNK = 25
# Individual calls already retry transient failures with backoff, so reaching
# this many *consecutive* exhausted chunks means the provider is genuinely
# refusing us. Grinding through hundreds more doomed calls would only deepen a
# rate limit while reporting a cheerful "done".
MAX_PROVIDER_FAILURES = 3
# A model can be retired between chunks. Repair and replay, but bound it so a
# provider retiring ids faster than we can adopt them cannot loop forever.
MAX_MODEL_REPAIRS = 2


def new_job(job_id: str) -> SyncJob:
    job = SyncJob(job_id=job_id)
    _JOBS[job_id] = job
    return job


def get_job(job_id: str) -> SyncJob | None:
    return _JOBS.get(job_id)


async def _run(conn: sqlite3.Connection, job: SyncJob) -> None:
    """Categorize every unresolved row in chunks, updating the job as it goes."""
    config = llm_config.resolve_config(conn)

    # Repair a retired model *before* spending the first call on it. This is
    # the check that turns "sync failed with a 404" into "sync ran".
    guard = await model_guard.ensure_usable_model(conn, config)
    config = guard.config
    available = guard.health.available
    if guard.switched:
        job.model_switched = guard.notice
        log.info("Sync continuing on replacement model %r", config.model)

    job.llm_available = available
    category_names = [c["name"] for c in repo.list_categories(conn)]

    rows = repo.list_uncategorized_transactions(conn)
    job.total = len(rows)

    provider_failures = 0
    model_repairs = 0
    start = 0

    while start < len(rows):
        chunk = rows[start : start + CHUNK]
        parsed_chunk = [
            ParsedRow(
                date=tx["date"],
                raw_description=tx["raw_description"],
                amount=tx["amount"],
                account_name=tx["account_name"],
            )
            for tx in chunk
        ]
        report: dict = {}
        outcomes = await categorization.categorize_rows_batch(
            conn,
            parsed_chunk,
            category_names,
            config,
            llm_available=available,
            report=report,
        )

        # The model died mid-run. Swap it out and replay this chunk against the
        # replacement rather than writing 25 rows off as uncategorized.
        if report.get("model_gone") and model_repairs < MAX_MODEL_REPAIRS:
            model_repairs += 1
            guard = await model_guard.ensure_usable_model(conn, config)
            if guard.switched:
                config = guard.config
                available = guard.health.available
                job.llm_available = available
                job.model_switched = guard.notice
                job.detail = None
                log.info("Replaying chunk at offset %d on %r", start, config.model)
                continue

        for tx, outcome in zip(chunk, outcomes, strict=False):
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
            else:
                job.still_uncategorized += 1
            job.processed += 1
        category_names = [c["name"] for c in repo.list_categories(conn)]
        # Commit per chunk so progress is durable and status reads see it.
        conn.commit()
        start += CHUNK

        if report.get("provider_error"):
            job.detail = report["provider_error"]
            provider_failures += 1
            log.warning(
                "Chunk failed (%d consecutive): %s",
                provider_failures,
                job.detail,
            )
            if provider_failures >= MAX_PROVIDER_FAILURES:
                job.stopped_early = True
                job.still_uncategorized += len(rows) - job.processed
                log.error(
                    "Stopping sync after %d consecutive failures", provider_failures
                )
                break
        else:
            # Only the *consecutive* counter resets. job.detail is left alone on
            # purpose: anything that reached this point already survived several
            # retries, so it explains rows that really did stay uncategorized
            # and the user should still see why.
            provider_failures = 0

    conn.commit()


async def run_sync_job(job_id: str) -> None:
    """Background entry point: opens its own connection and runs the sync."""
    job = _JOBS[job_id]
    job.state = "running"
    try:
        with session() as conn:
            await _run(conn, job)
        job.state = "done"
        log.info(
            "Sync %s done: %d/%d recategorized (%d cache, %d llm), %d left",
            job_id,
            job.recategorized,
            job.total,
            job.cache_hits,
            job.llm_cleaned,
            job.still_uncategorized,
        )
    except Exception as exc:  # pragma: no cover - defensive
        job.state = "error"
        job.error = str(exc)
        log.exception("Sync %s failed", job_id)


async def resync(conn: sqlite3.Connection) -> SyncJob:
    """Synchronous helper (used by tests): run the sync on a given connection."""
    job = SyncJob(job_id="inline")
    job.state = "running"
    await _run(conn, job)
    job.state = "done"
    return job
