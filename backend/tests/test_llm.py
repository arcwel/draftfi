"""Phase 3.6 — LLM JSON parsing (valid, malformed, wrapped) + error paths."""
from __future__ import annotations

import pytest

from app.services import llm
from app.services.llm import LLMError, parse_model_json
from app.services.llm_config import LLMConfig

OLLAMA = LLMConfig(
    provider="ollama",
    model="llama3.2",
    base_url="http://localhost:11434",
    api_key=None,
)


def test_parse_clean_json():
    r = parse_model_json('{"clean_merchant": "Amazon", "category": "Shopping"}')
    assert r.clean_merchant == "Amazon"
    assert r.category == "Shopping"


def test_parse_json_with_code_fence():
    text = '```json\n{"clean_merchant": "Netflix", "category": "Entertainment"}\n```'
    r = parse_model_json(text)
    assert r.clean_merchant == "Netflix"


def test_parse_json_embedded_in_prose():
    text = 'Sure! Here is the result: {"clean_merchant": "Shell", "category": "Transportation"} Hope this helps.'
    r = parse_model_json(text)
    assert r.clean_merchant == "Shell"
    assert r.category == "Transportation"


def test_parse_defaults_on_missing_category():
    r = parse_model_json('{"clean_merchant": "Mystery"}')
    assert r.clean_merchant == "Mystery"
    assert r.category == "Uncategorized"


def test_parse_raises_on_garbage():
    with pytest.raises(LLMError):
        parse_model_json("the model refused to answer")


@pytest.mark.asyncio
async def test_clean_merchant_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def fake_generate(config, prompt, system):
        calls["n"] += 1
        if calls["n"] == 1:
            return "no json here"
        return '{"clean_merchant": "Uber", "category": "Transportation"}'

    monkeypatch.setattr(llm, "_generate", fake_generate)
    result = await llm.clean_merchant(
        OLLAMA, "UBER TRIP", ["Transportation"], retries=1
    )
    assert result.clean_merchant == "Uber"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_clean_merchant_unreachable_raises(monkeypatch):
    import httpx

    async def boom(config, prompt, system):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm, "_generate", boom)
    with pytest.raises(LLMError):
        await llm.clean_merchant(OLLAMA, "X", ["Shopping"])


@pytest.mark.asyncio
async def test_health_requires_key_for_cloud_provider():
    cfg = LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        api_key=None,
    )
    available, latency, detail = await llm.health(cfg)
    assert available is False
    assert "key" in (detail or "").lower()
