"""One-time repair: re-apply the deterministic layer to rows it never saw.

The rule and transfer layers added in 2.0.1 only ran against rows still marked
Uncategorized. Anything the previous pipeline had already labelled kept its old
answer forever, so on a real file 1,117 rows sat in a category the current logic
disagrees with — 284 internal savings transfers filed as "Savings &
Investments", 202 transfers from the user's own account filed as "Income", 83
credit-card payments filed as "Fees & Interest".

What this deliberately does NOT touch:

* **User overrides.** ``source='user'`` and ``resolution='override'`` are never
  reconsidered. That is the whole promise of a manual correction.
* **Ambiguous merchants.** A warehouse club, a petrol station attached to a
  supermarket, or a convenience store genuinely spans categories, and the rule
  table's opinion is not better than an existing judgement. Overwriting those
  would be imposing a guess, not fixing an error.
"""
from __future__ import annotations

import logging
import sqlite3

from app.db import repository as repo
from app.services import descriptors, merchant_rules

log = logging.getLogger("draftfi.recategorize")

REPAIR_FLAG = "deterministic_repair_v1"


def _uncategorized_id(conn: sqlite3.Connection) -> int | None:
    row = repo.get_category_by_name(conn, merchant_rules.UNCATEGORIZED)
    return int(row["id"]) if row else None


def apply_deterministic_repair(conn: sqlite3.Connection) -> dict[str, int]:
    """Correct rows the current rule/transfer layer disagrees with.

    Returns a per-reason count. Idempotent via an ``app_settings`` flag, because
    re-running it would fight with any correction the user made afterwards.
    """
    done = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (REPAIR_FLAG,)
    ).fetchone()
    if done and done[0]:
        return {}

    uncategorized_id = _uncategorized_id(conn)
    rows = conn.execute(
        "SELECT t.id, t.raw_description, t.amount, t.canonical_key, t.resolution, "
        "       t.category_id, c.name AS current_category, mc.source AS memo_source "
        "FROM transactions t "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "LEFT JOIN merchant_category mc ON mc.canonical_key = t.canonical_key "
        "WHERE t.is_split_parent = 0"
    ).fetchall()

    stats = {"transfers": 0, "rules": 0, "skipped_ambiguous": 0, "protected": 0}
    category_ids: dict[str, int] = {}

    for row in rows:
        if row["resolution"] == "override" or row["memo_source"] == "user":
            stats["protected"] += 1
            continue

        key = row["canonical_key"] or descriptors.canonical_key(row["raw_description"])
        match = merchant_rules.resolve(key, row["amount"])
        if match is None or match.category == row["current_category"]:
            continue

        is_uncategorized = (
            row["category_id"] is None or row["category_id"] == uncategorized_id
        )
        if match.source == "transfer":
            reason = "transfers"
        elif is_uncategorized:
            # Nothing to lose: there was no real category here.
            reason = "rules"
        elif merchant_rules.is_ambiguous(key):
            stats["skipped_ambiguous"] += 1
            continue
        else:
            reason = "rules"

        if match.category not in category_ids:
            existing = repo.get_category_by_name(conn, match.category)
            category_ids[match.category] = (
                int(existing["id"])
                if existing
                else repo.upsert_category(conn, match.category, "#64748B")
            )
        repo.apply_categorization(
            conn,
            int(row["id"]),
            category_ids[match.category],
            descriptors.display_name(key),
            match.source,
            canonical_key=key,
        )
        stats[reason] += 1

    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, '1') "
        "ON CONFLICT(key) DO UPDATE SET value = '1'",
        (REPAIR_FLAG,),
    )
    conn.commit()
    if stats["transfers"] or stats["rules"]:
        log.warning(
            "Recategorized %d transfers and %d rule matches; left %d ambiguous "
            "merchants and %d user decisions alone.",
            stats["transfers"],
            stats["rules"],
            stats["skipped_ambiguous"],
            stats["protected"],
        )
    return stats
