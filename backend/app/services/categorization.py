"""Tiered categorization: normalize, then resolve as cheaply as possible.

Resolution order, first hit wins. The ordering is the design — it puts the
things we *know* ahead of the things we *guess*, and makes the answer stable:

1. ``user``     — a manual override. Permanent, outranks everything, forever.
2. ``transfer`` — money movement (card payments, Venmo, payroll). Structural,
                  not a judgement, and must precede merchant rules so
                  "CAPITAL ONE MOBILE PMT" can't be read as a merchant.
3. ``rule``     — seeded merchant table. Deterministic and free.
4. ``memo``     — a decision already made for this merchant, from any source.
                  This is the real cache, and it is what guarantees one merchant
                  keeps one category instead of drifting between batches.
5. ``llm``      — genuinely unknown merchants only, then written back to the
                  memo so it is never asked twice.

The key change from the previous design: everything is keyed on the *canonical
merchant key* from :mod:`services.descriptors`, not the raw descriptor. Raw
strings carry per-transaction junk, so keying on them meant near-zero cache
reuse and a fresh (inconsistent) model opinion for every variant.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from app.db import repository as repo
from app.services import descriptors, llm, merchant_rules
from app.services.csv_parser import ParsedRow
from app.services.llm_config import LLMConfig

log = logging.getLogger("draftfi.categorization")

UNCATEGORIZED = merchant_rules.UNCATEGORIZED

# Below this the model's own answer is discarded and the row is left for review.
# An LLM benchmark on this task scored 80% overall but 0% on rare categories —
# it guesses confidently rather than abstaining, so we need our own floor.
MIN_LLM_CONFIDENCE = 0.55

# One model call covers this many distinct merchants. Deliberately smaller than
# the old 25: batching research only validates up to ~6 items and shows accuracy
# degrading on harder tasks as batches grow. Because these are deduped merchants
# rather than transactions, 8 keys still covers far more than 8 rows.
MERCHANT_BATCH = 8


@dataclass
class Categorized:
    clean_merchant: str
    category_id: int | None
    resolution: str  # 'cache' | 'llm' | 'rule' | 'transfer' | 'uncategorized'
    # Cached onto the transaction row so override propagation and grouping never
    # have to re-run the normalizer over the whole table.
    canonical_key: str = ""


def _resolve_category_id(conn: sqlite3.Connection, category_name: str) -> int:
    """Map a category name to an id, creating it on first sight."""
    existing = repo.get_category_by_name(conn, category_name)
    if existing:
        return int(existing["id"])
    return repo.upsert_category(conn, category_name, "#64748B")


def _deterministic(
    conn: sqlite3.Connection, key: str, amount: float | None
) -> tuple[int, str] | None:
    """Tiers 1-4: user override, transfer/flow, seeded rule, existing memo."""
    memo = repo.get_merchant_decision(conn, key)
    # The category_id check is not redundant: the FK is ON DELETE SET NULL, so a
    # deleted category leaves a user decision pointing at nothing. int(None)
    # raised a TypeError that escaped all the way out of the import job.
    if memo and memo["source"] == "user" and memo["category_id"] is not None:
        return int(memo["category_id"]), "override"

    match = merchant_rules.resolve(key, amount)
    if match is not None:
        return _resolve_category_id(conn, match.category), match.source

    if memo and memo["category_id"] is not None:
        return int(memo["category_id"]), "cache"
    return None


def resolve_known(
    conn: sqlite3.Connection, raw_description: str, amount: float | None = None
) -> tuple[descriptors.Descriptor, tuple[int, str] | None]:
    """Normalize and try every non-LLM tier. Public for reuse at import time."""
    descriptor = descriptors.normalize(raw_description)
    return descriptor, _deterministic(conn, descriptor.key, amount)


async def categorize_row(
    conn: sqlite3.Connection,
    row: ParsedRow,
    category_names: list[str],
    config: LLMConfig | None = None,
    *,
    llm_available: bool = True,
) -> Categorized:
    """Resolve a single row through the tiered pipeline."""
    results = await categorize_rows_batch(
        conn, [row], category_names, config, llm_available=llm_available
    )
    return results[0]


async def _ask_model(
    conn: sqlite3.Connection,
    config: LLMConfig,
    keys: list[str],
    category_names: list[str],
    report: dict | None,
) -> dict[str, tuple[int, str]]:
    """Classify unknown merchants, smallest number of calls possible.

    Returns key -> (category_id, resolution). Keys the model declined or
    answered with low confidence are simply absent.
    """
    decided: dict[str, tuple[int, str]] = {}
    for start in range(0, len(keys), MERCHANT_BATCH):
        chunk = keys[start : start + MERCHANT_BATCH]
        try:
            answers = await llm.classify_merchants(config, chunk, category_names)
        except llm.ModelUnavailable as exc:
            if report is not None:
                report["provider_error"] = str(exc)
                report["model_gone"] = True
            break
        except llm.LLMUnavailable as exc:
            if report is not None:
                report["provider_error"] = str(exc)
            break
        except llm.LLMError as exc:
            log.info("Unusable model output for %d merchants: %s", len(chunk), exc)
            continue

        for key, answer in zip(chunk, answers, strict=False):
            if answer is None:
                continue
            if answer.category == UNCATEGORIZED:
                continue
            if answer.confidence is not None and answer.confidence < MIN_LLM_CONFIDENCE:
                log.info(
                    "Discarding low-confidence guess %r for %r (%.2f)",
                    answer.category, key, answer.confidence,
                )
                continue
            category_id = _resolve_category_id(conn, answer.category)
            repo.put_merchant_decision(
                conn,
                canonical_key=key,
                display_name=answer.display_name or descriptors.display_name(key),
                category_id=category_id,
                source="llm",
                confidence=answer.confidence,
            )
            decided[key] = (category_id, "llm")
    return decided


async def categorize_rows_batch(
    conn: sqlite3.Connection,
    rows: list[ParsedRow],
    category_names: list[str],
    config: LLMConfig | None = None,
    *,
    llm_available: bool = True,
    report: dict | None = None,
) -> list[Categorized]:
    """Resolve many rows: deterministic tiers first, one model pass for the rest.

    Pass ``report`` (a dict) to learn *why* rows went unresolved: on a provider
    failure it receives ``provider_error`` (and ``model_gone`` when the model id
    is retired), so the caller can surface a real message instead of silently
    returning a pile of Uncategorized rows.
    """
    if not rows:
        return []

    uncategorized_id = _resolve_category_id(conn, UNCATEGORIZED)
    normalized = [descriptors.normalize(r.raw_description) for r in rows]
    resolved: list[tuple[int, str] | None] = []
    unknown: list[str] = []

    for descriptor, row in zip(normalized, rows, strict=False):
        outcome = _deterministic(conn, descriptor.key, row.amount)
        resolved.append(outcome)
        if outcome is None and descriptor.key not in unknown:
            unknown.append(descriptor.key)

    if unknown and llm_available and config is not None:
        decided = await _ask_model(conn, config, unknown, category_names, report)
        if decided:
            for i, (descriptor, outcome) in enumerate(
                zip(normalized, resolved, strict=False)
            ):
                if outcome is None and descriptor.key in decided:
                    resolved[i] = decided[descriptor.key]

    results: list[Categorized] = []
    for descriptor, outcome in zip(normalized, resolved, strict=False):
        if outcome is None:
            results.append(
                Categorized(
                    clean_merchant=descriptor.display,
                    category_id=uncategorized_id,
                    resolution="uncategorized",
                    canonical_key=descriptor.key,
                )
            )
        else:
            category_id, resolution = outcome
            results.append(
                Categorized(
                    clean_merchant=descriptor.display,
                    category_id=category_id,
                    resolution=resolution,
                    canonical_key=descriptor.key,
                )
            )
    return results
