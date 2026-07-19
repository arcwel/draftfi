"""Import orchestration: parse -> categorize -> persist, with live status.

Handles CSV/OFX/QFX/QIF, multiple files in one job, and CSV column-mapping
memory (a bank's manually-mapped layout is remembered and reapplied on future
imports). A tiny in-process job registry backs the frontend progress UI.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field

from app.db import repository as repo
from app.db.connection import session
from app.services import categorization, llm, llm_config
from app.services.csv_parser import ParsedRow, header_signature
from app.services.statement_parsers import parse_statement, sniff_format

CHUNK = 25


@dataclass
class JobStatus:
    job_id: str
    # pending | parsing | categorizing | done | error | needs_mapping
    state: str = "pending"
    total: int = 0
    processed: int = 0
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_invalid: int = 0
    cache_hits: int = 0
    llm_cleaned: int = 0
    uncategorized: int = 0
    errors: list[str] = field(default_factory=list)
    # Set when a single CSV needs manual column mapping.
    headers: list[str] = field(default_factory=list)
    sample_rows: list[list[str]] = field(default_factory=list)
    signature: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_JOBS: dict[str, JobStatus] = {}


def new_job(job_id: str) -> JobStatus:
    status = JobStatus(job_id=job_id)
    _JOBS[job_id] = status
    return status


def get_job(job_id: str) -> JobStatus | None:
    return _JOBS.get(job_id)


# --------------------------------------------------------------------------- #
# CSV column-mapping memory (stored in app_settings, keyed by header signature)
# --------------------------------------------------------------------------- #
def _mapping_key(signature: str) -> str:
    return f"csv_mapping:{signature}"


def load_mapping(conn: sqlite3.Connection, signature: str) -> dict | None:
    raw = repo.get_setting(conn, _mapping_key(signature))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def save_mapping(conn: sqlite3.Connection, signature: str, mapping: dict) -> None:
    repo.set_setting(conn, _mapping_key(signature), json.dumps(mapping))


async def run_import(
    conn: sqlite3.Connection,
    files: list[tuple[str, bytes]],
    account_hint: str,
    status: JobStatus,
    mapping: dict[str, str] | None = None,
) -> JobStatus:
    """Parse every file, then categorize the combined rows in chunks."""
    status.state = "parsing"
    pending: list[ParsedRow] = []
    single = len(files) == 1

    for filename, content in files:
        report = parse_statement(filename, content, account_hint, mapping=mapping)

        # CSV whose auto-detect failed: try a remembered mapping for this bank.
        if report.mapping_failed and mapping is None and report.headers:
            sig = header_signature(report.headers)
            saved = load_mapping(conn, sig)
            if saved:
                report = parse_statement(
                    filename, content, account_hint, mapping=saved
                )

        if report.mapping_failed:
            if single:
                # Ask the user to map the columns (interactive dialog).
                status.state = "needs_mapping"
                status.headers = report.headers
                status.sample_rows = report.sample_rows
                status.signature = header_signature(report.headers)
                status.errors = report.errors
                return status
            # Multi-file: skip the unmappable file, keep going.
            status.errors.append(f"{filename}: could not detect columns; skipped.")
            continue

        status.errors.extend(f"{filename}: {e}" for e in report.errors)
        status.skipped_invalid += len(report.errors)
        pending.extend(report.rows)

        # Remember a manually-supplied mapping so this bank imports cleanly next
        # time (only for CSV, which has a header signature).
        if mapping and sniff_format(filename, content) == "csv" and report.headers:
            save_mapping(conn, header_signature(report.headers), mapping)

    status.total = len(pending)
    status.state = "categorizing"
    config = llm_config.resolve_config(conn)
    available, _, _ = await llm.health(config)
    category_names = [c["name"] for c in repo.list_categories(conn)]

    # Skip rows already stored (additive/non-destructive) before any LLM work.
    fresh: list[ParsedRow] = []
    for row in pending:
        if repo.transaction_exists(conn, row.import_hash):
            status.processed += 1
            status.skipped_duplicates += 1
        else:
            fresh.append(row)

    for start in range(0, len(fresh), CHUNK):
        chunk = fresh[start : start + CHUNK]
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
                status.skipped_duplicates += 1
                continue
            status.imported += 1
            if result.resolution == "cache":
                status.cache_hits += 1
            elif result.resolution == "llm":
                status.llm_cleaned += 1
            else:
                status.uncategorized += 1
        category_names = [c["name"] for c in repo.list_categories(conn)]
        conn.commit()

    conn.commit()
    status.state = "done"
    return status


async def run_import_job(
    job_id: str,
    files: list[tuple[str, bytes]],
    account_hint: str,
    mapping: dict[str, str] | None = None,
) -> None:
    """Background entry point: opens its own connection and runs the import."""
    job = _JOBS.get(job_id)
    if job is None:
        return
    try:
        with session() as conn:
            await run_import(conn, files, account_hint, job, mapping=mapping)
    except Exception as exc:  # pragma: no cover - defensive
        job.state = "error"
        job.errors.append(str(exc))
