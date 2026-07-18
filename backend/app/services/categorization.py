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
