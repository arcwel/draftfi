"""Sync: reprocess data that couldn't be resolved before.

The headline job is re-categorizing transactions that came in as
"Uncategorized" — typically because they were imported while no LLM was
reachable. Running sync after connecting a provider (or after the cache learned
a rule from a manual override) resolves them through the same cache-first
pipeline used on import.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db import repository as repo
from app.services import categorization, llm, llm_config
from app.services.csv_parser import ParsedRow


@dataclass
class SyncResult:
    scanned: int = 0
    recategorized: int = 0
    cache_hits: int = 0
    llm_cleaned: int = 0
    still_uncategorized: int = 0
    llm_available: bool = False

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "recategorized": self.recategorized,
            "cache_hits": self.cache_hits,
            "llm_cleaned": self.llm_cleaned,
            "still_uncategorized": self.still_uncategorized,
            "llm_available": self.llm_available,
        }


async def resync(conn: sqlite3.Connection) -> SyncResult:
    """Re-run categorization over every unresolved transaction."""
    config = llm_config.resolve_config(conn)
    available, _, _ = await llm.health(config)
    category_names = [c["name"] for c in repo.list_categories(conn)]

    rows = repo.list_uncategorized_transactions(conn)
    result = SyncResult(scanned=len(rows), llm_available=available)

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
            result.recategorized += 1
            if outcome.resolution == "cache":
                result.cache_hits += 1
            else:
                result.llm_cleaned += 1
                # A new category may have been created by the model.
                category_names = [c["name"] for c in repo.list_categories(conn)]
        else:
            result.still_uncategorized += 1

    conn.commit()
    return result
