"""LLM provider configuration resolved from the local ``app_settings`` table.

Supports four providers behind one interface:

* ``ollama``    — fully local, no API key, the privacy-preserving default.
* ``openai``    — ChatGPT (cloud).
* ``anthropic`` — Claude (cloud).
* ``gemini``    — Google Gemini (cloud).

Provider config and API keys live in the same ``sandbox.db`` as everything
else. Keys are stored per provider so switching providers doesn't lose them.
The raw key value is never sent back to the frontend — only a ``has_key`` flag.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from app.db import repository as repo

try:  # OS keychain is optional — headless/CI installs fall back to plaintext.
    import keyring
except Exception:  # pragma: no cover - keyring not installed
    keyring = None

# When a key lives in the OS keychain, app_settings only stores this marker
# (never the secret). Legacy/fallback rows store the plaintext key directly.
KEYRING_SERVICE = "DraftFi"
_KEYRING_MARKER = "__keyring__"
_keyring_state: bool | None = None


# --------------------------------------------------------------------------- #
# Provider registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    requires_key: bool
    default_model: str
    default_base_url: str
    is_local: bool
    model_hint: str


PROVIDERS: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        id="ollama",
        label="Ollama (local)",
        requires_key=False,
        default_model="llama3.2",
        default_base_url="http://localhost:11434",
        is_local=True,
        model_hint="e.g. llama3.2, mistral, qwen2.5",
    ),
    "openai": ProviderSpec(
        id="openai",
        label="ChatGPT (OpenAI)",
        requires_key=True,
        default_model="gpt-4o-mini",
        default_base_url="https://api.openai.com/v1",
        is_local=False,
        model_hint="e.g. gpt-4o-mini, gpt-4o",
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        label="Claude (Anthropic)",
        requires_key=True,
        default_model="claude-haiku-4-5-20251001",
        default_base_url="https://api.anthropic.com",
        is_local=False,
        model_hint="e.g. claude-haiku-4-5, claude-sonnet-4-5",
    ),
    "gemini": ProviderSpec(
        id="gemini",
        label="Gemini (Google)",
        requires_key=True,
        default_model="gemini-2.0-flash",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        is_local=False,
        model_hint="e.g. gemini-2.0-flash, gemini-1.5-flash",
    ),
}

DEFAULT_PROVIDER = "ollama"

# app_settings keys
K_PROVIDER = "llm_provider"
K_MODEL = "llm_model"
K_BASE_URL = "llm_base_url"


def _key_setting(provider: str) -> str:
    return f"llm_api_key:{provider}"


def _keyring_usable() -> bool:
    """True when the OS keychain can round-trip a secret (probed once, cached).

    Set ``DRAFTFI_NO_KEYRING=1`` to force plaintext (headless servers, tests).
    """
    global _keyring_state
    if _keyring_state is not None:
        return _keyring_state
    if keyring is None or os.environ.get("DRAFTFI_NO_KEYRING"):
        _keyring_state = False
        return False
    try:
        probe = f"{KEYRING_SERVICE}:probe"
        keyring.set_password(KEYRING_SERVICE, probe, "1")
        ok = keyring.get_password(KEYRING_SERVICE, probe) == "1"
        keyring.delete_password(KEYRING_SERVICE, probe)
        _keyring_state = bool(ok)
    except Exception:
        _keyring_state = False
    return _keyring_state


def _store_key(conn: sqlite3.Connection, provider: str, api_key: str) -> None:
    """Persist a key to the OS keychain (marker in the DB), else plaintext."""
    key_id = _key_setting(provider)
    if _keyring_usable():
        try:
            keyring.set_password(KEYRING_SERVICE, key_id, api_key)
            repo.set_setting(conn, key_id, _KEYRING_MARKER)
            return
        except Exception:  # pragma: no cover - keychain write failed at runtime
            pass
    repo.set_setting(conn, key_id, api_key)


@dataclass
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str | None

    @property
    def spec(self) -> ProviderSpec:
        return PROVIDERS[self.provider]


def resolve_config(conn: sqlite3.Connection) -> LLMConfig:
    """Build the active LLM config from stored settings + provider defaults."""
    settings = repo.get_settings_map(conn)
    provider = settings.get(K_PROVIDER, DEFAULT_PROVIDER)
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    spec = PROVIDERS[provider]
    return LLMConfig(
        provider=provider,
        model=settings.get(K_MODEL) or spec.default_model,
        base_url=settings.get(K_BASE_URL) or spec.default_base_url,
        api_key=settings.get(_key_setting(provider)),
    )


def save_config(
    conn: sqlite3.Connection,
    *,
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> None:
    """Persist provider selection, model, base URL, and (optionally) an API key.

    ``model``/``base_url`` fall back to provider defaults when blank so a fresh
    provider switch always yields a working config. An ``api_key`` is only
    written when a non-empty value is supplied — this preserves an existing key
    when the user updates model/base_url without re-entering the secret.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    spec = PROVIDERS[provider]

    repo.set_setting(conn, K_PROVIDER, provider)
    repo.set_setting(conn, K_MODEL, (model or "").strip() or spec.default_model)
    repo.set_setting(
        conn, K_BASE_URL, (base_url or "").strip() or spec.default_base_url
    )
    if api_key is not None and api_key.strip():
        _store_key(conn, provider, api_key.strip())


def has_key(conn: sqlite3.Connection, provider: str) -> bool:
    """A key exists when the DB has a marker or plaintext row for the provider."""
    return bool(repo.get_setting(conn, _key_setting(provider)))


def get_key(conn: sqlite3.Connection, provider: str) -> str | None:
    """Return the stored API key for a provider (or None).

    Resolves the keychain when the row is a marker; otherwise it's a legacy or
    fallback plaintext value.
    """
    key_id = _key_setting(provider)
    stored = repo.get_setting(conn, key_id)
    if not stored:
        return None
    if stored == _KEYRING_MARKER:
        try:
            return keyring.get_password(KEYRING_SERVICE, key_id)
        except Exception:  # pragma: no cover - keychain read failed at runtime
            return None
    return stored


def clear_key(conn: sqlite3.Connection, provider: str) -> None:
    key_id = _key_setting(provider)
    if repo.get_setting(conn, key_id) == _KEYRING_MARKER:
        try:
            keyring.delete_password(KEYRING_SERVICE, key_id)
        except Exception:  # pragma: no cover
            pass
    repo.set_setting(conn, key_id, None)
