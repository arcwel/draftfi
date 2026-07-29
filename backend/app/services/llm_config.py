"""LLM provider configuration resolved from the local ``app_settings`` table.

Supports four providers behind one interface:

* ``ollama``    — fully local, no API key, the privacy-preserving default.
* ``openai``    — ChatGPT (cloud).
* ``anthropic`` — Claude (cloud).
* ``gemini``    — Google Gemini (cloud).

Provider config and API keys live in the same ``sandbox.db`` as everything
else. Keys are stored per provider so switching providers doesn't lose them.
The raw key value is never sent back to the frontend — only a ``has_key`` flag.

Cloud providers retire model ids on their own schedule, which silently breaks a
config that worked for months. This module therefore also owns the *repair*
side: :func:`pick_replacement_model` chooses a live substitute, and the notice
helpers record what changed so the UI can tell the user after the fact instead
of blocking them with an error.
"""
from __future__ import annotations

import json
import os
import re
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
    # Ranked substitutes tried first when the configured model is retired.
    # Aliases that track "whatever is current" come first on purpose: they are
    # the only ids that cannot go stale the way a pinned version does.
    fallback_models: tuple[str, ...] = ()


PROVIDERS: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        id="ollama",
        label="Ollama (local)",
        requires_key=False,
        default_model="llama3.2",
        default_base_url="http://localhost:11434",
        is_local=True,
        model_hint="e.g. llama3.2, mistral, qwen2.5",
        fallback_models=("llama3.2", "llama3.1", "mistral", "qwen2.5"),
    ),
    "openai": ProviderSpec(
        id="openai",
        label="ChatGPT (OpenAI)",
        requires_key=True,
        default_model="gpt-4o-mini",
        default_base_url="https://api.openai.com/v1",
        is_local=False,
        model_hint=(
            "e.g. gpt-4o-mini, gpt-4o \u2014 auto-corrected if retired"
        ),
        fallback_models=("gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"),
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        label="Claude (Anthropic)",
        requires_key=True,
        default_model="claude-haiku-4-5-20251001",
        default_base_url="https://api.anthropic.com",
        is_local=False,
        model_hint=(
            "e.g. claude-haiku-4-5, claude-sonnet-4-5 \u2014 auto-corrected if retired"
        ),
        fallback_models=("claude-haiku-4-5", "claude-sonnet-4-5"),
    ),
    "gemini": ProviderSpec(
        id="gemini",
        label="Gemini (Google)",
        requires_key=True,
        default_model="gemini-flash-latest",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        is_local=False,
        model_hint=(
            "e.g. gemini-flash-latest, gemini-3.6-flash "
            "\u2014 auto-corrected if retired"
        ),
        fallback_models=(
            "gemini-flash-latest",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-flash-preview",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
        ),
    ),
}

DEFAULT_PROVIDER = "ollama"

# app_settings keys
K_PROVIDER = "llm_provider"
K_MODEL = "llm_model"
K_BASE_URL = "llm_base_url"
# A pending "we switched your model for you" message, shown once and dismissed.
K_MODEL_NOTICE = "llm_model_notice"


# --------------------------------------------------------------------------- #
# Model selection / repair
# --------------------------------------------------------------------------- #
# Categorization is a cheap, high-volume, strict-JSON task, so a text "flash"
# tier model is always the right pick. Anything specialised for another
# modality would either fail outright or cost far more for no benefit.
_MODALITY_EXCLUDE = re.compile(
    r"(image|vision|audio|tts|speech|video|embed|embedding|aqa|live|realtime|"
    r"computer-use|imagen|veo|whisper|dall-?e|moderation|rerank|guard)",
    re.IGNORECASE,
)
# Preview/experimental ids churn fastest; usable, but only if nothing else fits.
_UNSTABLE = re.compile(r"(preview|exp|experimental|beta|alpha|nightly)", re.IGNORECASE)
_CHEAP_TIER = re.compile(r"(flash|mini|haiku|lite|small|turbo)", re.IGNORECASE)
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)")


def _version_key(name: str) -> tuple:
    """Sort key from the numbers in a model id — 3.6 ranks above 3.5 above 2.0."""
    match = _VERSION_RE.search(name)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _score(name: str) -> tuple:
    """Rank a candidate model. Higher is better."""
    return (
        0 if _MODALITY_EXCLUDE.search(name) else 1,
        1 if _CHEAP_TIER.search(name) else 0,
        1 if "latest" in name.lower() else 0,
        0 if _UNSTABLE.search(name) else 1,
        _version_key(name),
        # Shorter ids are the canonical alias (`gemini-2.0-flash` over
        # `gemini-2.0-flash-001`), which is the more durable thing to pin to.
        -len(name),
    )


def pick_replacement_model(
    provider: str,
    available: list[str] | None,
    current: str | None = None,
) -> str | None:
    """Choose a live model to replace a retired ``current``.

    Prefers the provider's ranked ``fallback_models`` when one of them is
    actually offered, then falls back to scoring whatever the provider lists.
    A purely static list would rot exactly the way the retired model did, so the
    heuristic path is the one that has to keep working. Returns ``None`` when
    there is nothing sensible to switch to (the caller then leaves the config
    alone rather than guessing).
    """
    spec = PROVIDERS.get(provider)
    offered = [m for m in (available or []) if m and m != current]

    if spec:
        offered_set = set(offered)
        for candidate in spec.fallback_models:
            if candidate != current and candidate in offered_set:
                return candidate

    usable = [m for m in offered if not _MODALITY_EXCLUDE.search(m)]
    if usable:
        return max(usable, key=_score)

    # The provider gave us nothing usable (or nothing at all). Fall back to the
    # ranked list blind — better a plausible guess than staying on a dead id.
    if spec:
        for candidate in spec.fallback_models:
            if candidate != current:
                return candidate
    return None


# --------------------------------------------------------------------------- #
# "We changed your model" notice
# --------------------------------------------------------------------------- #
def record_model_notice(
    conn: sqlite3.Connection,
    *,
    provider: str,
    previous_model: str,
    new_model: str,
    reason: str | None = None,
) -> dict:
    """Persist a dismissible note that DraftFi repaired the model selection."""
    notice = {
        "provider": provider,
        "previous_model": previous_model,
        "new_model": new_model,
        "reason": reason or "",
    }
    repo.set_setting(conn, K_MODEL_NOTICE, json.dumps(notice))
    return notice


def get_model_notice(conn: sqlite3.Connection) -> dict | None:
    raw = repo.get_setting(conn, K_MODEL_NOTICE)
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def clear_model_notice(conn: sqlite3.Connection) -> None:
    repo.set_setting(conn, K_MODEL_NOTICE, None)


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
        # Resolve through the keychain — the DB row may be only a marker (G1),
        # so never hand the raw setting value to the provider.
        api_key=get_key(conn, provider),
    )


def set_model(conn: sqlite3.Connection, model: str) -> None:
    """Update only the active model, leaving provider/base URL/key untouched."""
    repo.set_setting(conn, K_MODEL, model)


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
