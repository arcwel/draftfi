"""Deterministic caching + categorization pipeline (PRD 6.1, 7).

For each ingested row:

1. Look up ``merchant_llm_cache`` by raw descriptor.
2. Cache hit  -> apply clean merchant + category instantly, tag ``cache``.
3. Cache miss -> call the local LLM, tag ``llm``, then write the mapping to
   the cache immediately so subsequent imports never re-query the model.
4. No LLM reachable -> tag ``uncategorized`` (graceful degradation) and leave
   the row for later re-categorization; nothing is written to the cache.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db import repository as repo
from app.services import llm
from app.services.csv_parser import ParsedRow
from app.services.llm_config import LLMConfig

UNCATEGORIZED = "Uncategorized"


@dataclass
class Categorized:
    clean_merchant: str
    category_id: int | None
    resolution: str  # 'cache' | 'llm' | 'uncategorized'


def _resolve_category_id(conn: sqlite3.Connection, category_name: str) -> int:
    """Map a category name to an id, creating it on first sight."""
    existing = repo.get_category_by_name(conn, category_name)
    if existing:
        return int(existing["id"])
    # Unknown category from the model — create it with a neutral color.
    return repo.upsert_category(conn, category_name, "#64748B")


async def categorize_row(
    conn: sqlite3.Connection,
    row: ParsedRow,
    category_names: list[str],
    config: LLMConfig | None = None,
    *,
    llm_available: bool = True,
) -> Categorized:
    """Resolve a single row through the cache-first pipeline."""
    cached = repo.get_cache(conn, row.raw_description)
    if cached is not None:
        return Categorized(
            clean_merchant=cached["clean_merchant"],
            category_id=cached["category_id"],
            resolution="cache",
        )

    if not llm_available or config is None:
        uncat_id = _resolve_category_id(conn, UNCATEGORIZED)
        return Categorized(
            clean_merchant=row.raw_description,
            category_id=uncat_id,
            resolution="uncategorized",
        )

    try:
        result = await llm.clean_merchant(config, row.raw_description, category_names)
    except llm.LLMError:
        uncat_id = _resolve_category_id(conn, UNCATEGORIZED)
        return Categorized(
            clean_merchant=row.raw_description,
            category_id=uncat_id,
            resolution="uncategorized",
        )

    category_id = _resolve_category_id(conn, result.category)
    # Persist on miss so future imports block redundant LLM cycles.
    repo.put_cache(conn, row.raw_description, result.clean_merchant, category_id)
    return Categorized(
        clean_merchant=result.clean_merchant,
        category_id=category_id,
        resolution="llm",
    )


async def categorize_rows_batch(
    conn: sqlite3.Connection,
    rows: list[ParsedRow],
    category_names: list[str],
    config: LLMConfig | None = None,
    *,
    llm_available: bool = True,
    report: dict | None = None,
) -> list[Categorized]:
    """Resolve many rows at once: cache-first, then ONE LLM call for the misses.

    Batching cuts a 500-row import from ~500 model calls to ~20. Rows the batch
    response fails to cover fall back to individual calls; anything still
    unresolved degrades to Uncategorized. Returns results aligned with ``rows``.

    Pass ``report`` (a dict) to learn *why* rows went unresolved: on a provider
    failure it receives ``provider_error``, so the caller can surface a real
    message instead of silently returning a pile of Uncategorized rows.
    """
    results: list[Categorized | None] = [None] * len(rows)
    uncat_id = _resolve_category_id(conn, UNCATEGORIZED)

    def uncategorized_for(row: ParsedRow) -> Categorized:
        return Categorized(
            clean_merchant=row.raw_description,
            category_id=uncat_id,
            resolution="uncategorized",
        )

    # Pass 1: cache hits (and duplicate descriptors within this same batch).
    misses: list[int] = []
    for i, row in enumerate(rows):
        cached = repo.get_cache(conn, row.raw_description)
        if cached is not None:
            results[i] = Categorized(
                clean_merchant=cached["clean_merchant"],
                category_id=cached["category_id"],
                resolution="cache",
            )
        else:
            misses.append(i)

    if not misses or not llm_available or config is None:
        for i in misses:
            results[i] = uncategorized_for(rows[i])
        return [r for r in results if r is not None]

    # Pass 2: one model call for the unique missing descriptors.
    unique: list[str] = []
    index_of: dict[str, int] = {}
    for i in misses:
        raw = rows[i].raw_description
        if raw not in index_of:
            index_of[raw] = len(unique)
            unique.append(raw)

    provider_error: str | None = None
    try:
        batch = await llm.clean_merchants_batch(config, unique, category_names)
    except llm.LLMUnavailable as exc:
        # The endpoint refused us (rate limit / auth / outage). Retrying each
        # row individually would multiply the load against a provider that is
        # already saying no, so skip pass 3 and report why nothing resolved.
        provider_error = str(exc)
        batch = [None] * len(unique)
    except llm.LLMError:
        batch = [None] * len(unique)

    if report is not None and provider_error:
        report["provider_error"] = provider_error

    for i in misses:
        row = rows[i]
        outcome = batch[index_of[row.raw_description]]
        if outcome is None:
            if provider_error:
                results[i] = uncategorized_for(row)
                continue
            # Pass 3: individual retry for stragglers the batch missed.
            try:
                outcome = await llm.clean_merchant(
                    config, row.raw_description, category_names
                )
            except llm.LLMUnavailable as exc:
                provider_error = str(exc)
                if report is not None:
                    report["provider_error"] = provider_error
                results[i] = uncategorized_for(row)
                continue
            except llm.LLMError:
                results[i] = uncategorized_for(row)
                continue
        # First resolution of a descriptor writes the cache; later duplicates
        # in this batch resolve from it via get_cache on their own imports.
        if repo.get_cache(conn, row.raw_description) is None:
            category_id = _resolve_category_id(conn, outcome.category)
            repo.put_cache(
                conn, row.raw_description, outcome.clean_merchant, category_id
            )
        else:
            category_id = _resolve_category_id(conn, outcome.category)
        results[i] = Categorized(
            clean_merchant=outcome.clean_merchant,
            category_id=category_id,
            resolution="llm",
        )

    return [r for r in results if r is not None]
