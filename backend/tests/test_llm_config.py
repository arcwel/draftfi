"""LLM provider config: persistence, key masking, provider switching."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.services import llm_config


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "cfg.db"
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(db_file))
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")
    importlib.reload(main)
    with TestClient(main.create_app()) as c:
        yield c


def test_default_is_ollama_local(client):
    cfg = client.get("/llm/config").json()
    assert cfg["provider"] == "ollama"
    assert cfg["model"] == "llama3.2"
    ids = {p["id"] for p in cfg["providers"]}
    assert ids == {"ollama", "openai", "anthropic", "gemini"}


def test_key_never_returned_only_has_key_flag(client):
    client.put(
        "/llm/config",
        json={"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-secret"},
    )
    body = client.get("/llm/config").json()
    assert body["provider"] == "openai"
    openai = next(p for p in body["providers"] if p["id"] == "openai")
    assert openai["has_key"] is True
    # The secret must not appear anywhere in the serialized response.
    assert "sk-secret" not in client.get("/llm/config").text


def test_key_persists_when_updating_model_without_reentering(client):
    client.put("/llm/config", json={"provider": "anthropic", "api_key": "ak-123"})
    # Update just the model — omit api_key.
    client.put("/llm/config", json={"provider": "anthropic", "model": "claude-sonnet-4-5"})
    body = client.get("/llm/config").json()
    anthropic = next(p for p in body["providers"] if p["id"] == "anthropic")
    assert anthropic["has_key"] is True
    assert body["model"] == "claude-sonnet-4-5"


def test_switching_provider_keeps_each_key(client):
    client.put("/llm/config", json={"provider": "openai", "api_key": "sk-a"})
    client.put("/llm/config", json={"provider": "gemini", "api_key": "gm-b"})
    body = client.get("/llm/config").json()
    by_id = {p["id"]: p for p in body["providers"]}
    assert by_id["openai"]["has_key"] is True
    assert by_id["gemini"]["has_key"] is True
    assert by_id["anthropic"]["has_key"] is False


def test_delete_key(client):
    client.put("/llm/config", json={"provider": "openai", "api_key": "sk-a"})
    client.delete("/llm/config/openai/key")
    body = client.get("/llm/config").json()
    openai = next(p for p in body["providers"] if p["id"] == "openai")
    assert openai["has_key"] is False


def test_unknown_provider_rejected(client):
    r = client.put("/llm/config", json={"provider": "bogus"})
    assert r.status_code == 400


def test_defaults_fill_in_on_blank_model(client):
    client.put("/llm/config", json={"provider": "gemini", "api_key": "gm"})
    body = client.get("/llm/config").json()
    assert body["model"] == llm_config.PROVIDERS["gemini"].default_model
