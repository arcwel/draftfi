"""Phase 4.7 — cache miss -> write -> hit, plus graceful degradation."""
from __future__ import annotations

import pytest

from app.db import repository as repo
from app.services import categorization, llm
from app.services.csv_parser import ParsedRow
from app.services.llm_config import LLMConfig

CONFIG = LLMConfig(
    provider="ollama",
    model="llama3.2",
    base_url="http://localhost:11434",
    api_key=None,
)


@pytest.mark.asyncio
async def test_miss_then_hit(conn, monkeypatch):
    async def fake_clean(config, raw, cats, retries=1):
        return llm.CleanResult(clean_merchant="Amazon", category="Shopping")

    monkeypatch.setattr(llm, "clean_merchant", fake_clean)
    names = [c["name"] for c in repo.list_categories(conn)]
    row = ParsedRow("2026-01-01", "AMZN MKTP US*2A34M1", -42.19, "Chase")

    # First pass: cache miss -> LLM -> tagged 'llm' and written to cache.
    first = await categorization.categorize_row(
        conn, row, names, CONFIG, llm_available=True
    )
    assert first.resolution == "llm"
    assert first.clean_merchant == "Amazon"
    assert repo.get_cache(conn, row.raw_description) is not None

    # Second pass: cache hit, no LLM needed.
    def boom(*a, **k):
        raise AssertionError("LLM should not be called on a cache hit")

    monkeypatch.setattr(llm, "clean_merchant", boom)
    second = await categorization.categorize_row(
        conn, row, names, CONFIG, llm_available=True
    )
    assert second.resolution == "cache"
    assert second.clean_merchant == "Amazon"


@pytest.mark.asyncio
async def test_graceful_degradation_when_llm_down(conn):
    names = [c["name"] for c in repo.list_categories(conn)]
    row = ParsedRow("2026-01-01", "UNKNOWN VENDOR", -10.0, "Chase")
    result = await categorization.categorize_row(
        conn, row, names, CONFIG, llm_available=False
    )
    assert result.resolution == "uncategorized"
    # Nothing written to cache when unresolved.
    assert repo.get_cache(conn, row.raw_description) is None


@pytest.mark.asyncio
async def test_llm_error_falls_back_to_uncategorized(conn, monkeypatch):
    async def boom(config, raw, cats, retries=1):
        raise llm.LLMError("model exploded")

    monkeypatch.setattr(llm, "clean_merchant", boom)
    names = [c["name"] for c in repo.list_categories(conn)]
    row = ParsedRow("2026-01-01", "FLAKY", -1.0, "Chase")
    result = await categorization.categorize_row(
        conn, row, names, CONFIG, llm_available=True
    )
    assert result.resolution == "uncategorized"
