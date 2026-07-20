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


# --------------------------------------------------------------------------- #
# G1 — API keys stored in the OS keychain (plaintext fallback)
# --------------------------------------------------------------------------- #
def test_key_stored_in_keychain_when_available(conn, monkeypatch):
    import types

    from app.db import repository as repo

    store = {}
    fake = types.SimpleNamespace(
        set_password=lambda s, u, p: store.__setitem__((s, u), p),
        get_password=lambda s, u: store.get((s, u)),
        delete_password=lambda s, u: store.pop((s, u), None),
    )
    monkeypatch.setattr(llm_config, "keyring", fake)
    monkeypatch.setattr(llm_config, "_keyring_state", None)
    monkeypatch.delenv("DRAFTFI_NO_KEYRING", raising=False)

    llm_config.save_config(conn, provider="openai", api_key="sk-secret")

    # The DB row holds only a marker — never the secret itself.
    assert repo.get_setting(conn, "llm_api_key:openai") == llm_config._KEYRING_MARKER
    assert ("DraftFi", "llm_api_key:openai") in store
    # And it resolves back through the keychain.
    assert llm_config.get_key(conn, "openai") == "sk-secret"
    assert llm_config.has_key(conn, "openai") is True

    llm_config.clear_key(conn, "openai")
    assert llm_config.get_key(conn, "openai") is None
    assert ("DraftFi", "llm_api_key:openai") not in store


def test_key_plaintext_fallback_without_keychain(conn, monkeypatch):
    from app.db import repository as repo

    monkeypatch.setattr(llm_config, "_keyring_state", None)
    monkeypatch.setenv("DRAFTFI_NO_KEYRING", "1")

    llm_config.save_config(conn, provider="openai", api_key="sk-plain")
    # Fallback stores the key directly (dev / headless).
    assert repo.get_setting(conn, "llm_api_key:openai") == "sk-plain"
    assert llm_config.get_key(conn, "openai") == "sk-plain"


def test_resolve_config_returns_real_key_not_marker(conn, monkeypatch):
    """Regression: resolve_config must resolve the keychain, not hand the
    '__keyring__' marker to providers (would send Bearer __keyring__ -> 401)."""
    import types

    store = {}
    fake = types.SimpleNamespace(
        set_password=lambda s, u, p: store.__setitem__((s, u), p),
        get_password=lambda s, u: store.get((s, u)),
        delete_password=lambda s, u: store.pop((s, u), None),
    )
    monkeypatch.setattr(llm_config, "keyring", fake)
    monkeypatch.setattr(llm_config, "_keyring_state", None)
    monkeypatch.delenv("DRAFTFI_NO_KEYRING", raising=False)

    llm_config.save_config(conn, provider="openai", model="gpt-4o-mini", api_key="sk-real")
    cfg = llm_config.resolve_config(conn)
    assert cfg.provider == "openai"
    assert cfg.api_key == "sk-real"
    assert cfg.api_key != llm_config._KEYRING_MARKER
