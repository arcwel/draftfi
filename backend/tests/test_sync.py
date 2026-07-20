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

    def _resolve(raw):
        if "AMZN" in raw:
            return llm.CleanResult(clean_merchant="Amazon", category="Shopping")
        return llm.CleanResult(clean_merchant="Shell", category="Transportation")

    # Mock the batch call — that's the path production actually takes.
    async def fake_batch(config, raws, cats):
        return [_resolve(r) for r in raws]

    async def fake_clean(config, raw, cats, retries=1):
        return _resolve(raw)

    monkeypatch.setattr(llm, "health", fake_health)
    monkeypatch.setattr(llm, "clean_merchants_batch", fake_batch)
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


@pytest.mark.asyncio
async def test_rate_limited_provider_is_reported_not_silently_swallowed(conn, monkeypatch):
    """A 429 must surface as a reason and stop the run, not report a clean 'done'
    while every row quietly stays Uncategorized."""
    for i in range(60):  # > 2 chunks so the early-abort path is exercised
        _add_uncategorized(conn, f"MERCHANT {i}", i)

    async def fake_health(config):
        return True, 5.0, None

    calls = {"batch": 0, "single": 0}

    async def rate_limited_batch(config, raws, cats):
        calls["batch"] += 1
        raise llm.LLMUnavailable("LLM endpoint error: Client error '429 Too Many Requests'")

    async def should_not_run(config, raw, cats, retries=1):
        calls["single"] += 1
        raise AssertionError("must not retry per-row against a refusing provider")

    monkeypatch.setattr(llm, "health", fake_health)
    monkeypatch.setattr(llm, "clean_merchants_batch", rate_limited_batch)
    monkeypatch.setattr(llm, "clean_merchant", should_not_run)

    result = await sync.resync(conn)

    assert result.recategorized == 0
    assert "429" in (result.detail or ""), "the real reason must reach the UI"
    assert result.stopped_early is True
    # Bailed out after the failure threshold instead of grinding every chunk...
    assert calls["batch"] == 2
    # ...and never amplified into per-row calls.
    assert calls["single"] == 0
    # Every row is still accounted for as unresolved.
    assert result.still_uncategorized == result.total
