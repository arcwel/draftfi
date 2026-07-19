"""Sync re-categorizes transactions that were left Uncategorized."""
from __future__ import annotations

import pytest

from app.db import repository as repo
from app.services import llm, sync


def _add_uncategorized(conn, raw, i):
    uncat = repo.upsert_category(conn, "Uncategorized", "#64748B")
    repo.insert_transaction(
        conn,
        {
            "date": f"2026-01-0{i + 1}",
            "raw_description": raw,
            "amount": -10.0,
            "account_name": "Checking",
            "category_id": uncat,
            "clean_merchant": raw,
            "resolution": "uncategorized",
            "import_hash": f"h{i}",
        },
    )


@pytest.mark.asyncio
async def test_sync_resolves_via_llm_when_available(conn, monkeypatch):
    _add_uncategorized(conn, "AMZN MKTP US", 0)
    _add_uncategorized(conn, "SHELL OIL 12", 1)

    async def fake_health(config):
        return True, 5.0, None

    async def fake_clean(config, raw, cats, retries=1):
        if "AMZN" in raw:
            return llm.CleanResult(clean_merchant="Amazon", category="Shopping")
        return llm.CleanResult(clean_merchant="Shell", category="Transportation")

    monkeypatch.setattr(llm, "health", fake_health)
    monkeypatch.setattr(llm, "clean_merchant", fake_clean)

    result = await sync.resync(conn)
    assert result.total == 2
    assert result.processed == 2
    assert result.recategorized == 2
    assert result.llm_cleaned == 2
    assert result.still_uncategorized == 0
    # The rows now carry real categories.
    rows = repo.list_transactions(conn)
    names = {r["category_name"] for r in rows}
    assert {"Shopping", "Transportation"} <= names


@pytest.mark.asyncio
async def test_sync_noop_when_llm_unavailable(conn, monkeypatch):
    _add_uncategorized(conn, "MYSTERY VENDOR", 0)

    async def offline(config):
        return False, None, "offline"

    monkeypatch.setattr(llm, "health", offline)

    result = await sync.resync(conn)
    assert result.total == 1
    assert result.recategorized == 0
    assert result.still_uncategorized == 1
    assert result.llm_available is False


@pytest.mark.asyncio
async def test_sync_uses_cache_without_llm_call(conn, monkeypatch):
    # A cache rule exists (e.g. from a prior override); sync should apply it
    # even though the LLM is offline.
    shopping = repo.upsert_category(conn, "Shopping", "#f97316")
    repo.put_cache(conn, "AMZN MKTP US", "Amazon", shopping)
    _add_uncategorized(conn, "AMZN MKTP US", 0)

    async def offline(config):
        return False, None, "offline"

    monkeypatch.setattr(llm, "health", offline)

    result = await sync.resync(conn)
    assert result.recategorized == 1
    assert result.cache_hits == 1
