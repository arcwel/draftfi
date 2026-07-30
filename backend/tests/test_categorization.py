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
    """An unknown merchant is asked once, then answered from the memo forever.

    Uses a merchant the seeded rules do NOT know — a known one resolves without
    any model call, which is a different (also tested) path.
    """
    async def fake_classify(config, merchants, cats):
        return [
            llm.MerchantVerdict(
                merchant="Zephyr Cycles", category="Shopping", confidence=0.9
            )
            for _ in merchants
        ]

    monkeypatch.setattr(llm, "classify_merchants", fake_classify)
    names = [c["name"] for c in repo.list_categories(conn)]
    row = ParsedRow("2026-01-01", "ZEPHYR CYCLES *2A34M1 PORTLAND OR", -42.19, "Chase")

    first = await categorization.categorize_row(
        conn, row, names, CONFIG, llm_available=True
    )
    assert first.resolution == "llm"
    assert first.clean_merchant == "Zephyr Cycles"
    # The decision is recorded against the canonical merchant, not the raw
    # string — that is what makes it reusable across descriptor variants.
    decision = repo.get_merchant_decision(conn, first.canonical_key)
    assert decision is not None
    assert decision["source"] == "llm"

    def boom(*a, **k):
        raise AssertionError("LLM should not be called once a decision exists")

    monkeypatch.setattr(llm, "classify_merchants", boom)

    # A *different* raw spelling of the same merchant also resolves for free.
    variant = ParsedRow("2026-02-02", "ZEPHYR CYCLES *99XQ7 PORTLAND OR", -8.0, "Chase")
    second = await categorization.categorize_row(
        conn, variant, names, CONFIG, llm_available=True
    )
    assert second.resolution == "cache"
    assert second.clean_merchant == "Zephyr Cycles"


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
