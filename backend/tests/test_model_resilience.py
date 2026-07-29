"""A retired model must never stop the user.

Covers the failure that motivated all of this: a provider retires the model id
in the user's config, keeps answering every other request, and still lists the
dead model in its own catalogue — so the app reported a healthy provider while
every categorization call 404'd.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from app.db import repository as repo
from app.services import llm, llm_config, logging_setup, model_guard, sync
from app.services.llm_config import LLMConfig

GEMINI_RETIRED_BODY = (
    '{"error": {"code": 404, "message": "This model '
    'models/gemini-3-pro-preview is no longer available. Please update your '
    'code to use a newer model.", "status": "NOT_FOUND"}}'
)


def _config(model: str = "gemini-3-pro-preview") -> LLMConfig:
    return LLMConfig(
        provider="gemini",
        model=model,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="test-key",
    )


# --------------------------------------------------------------------------- #
# Recognising a dead model id
# --------------------------------------------------------------------------- #
def test_retired_model_response_is_recognised():
    assert llm._is_model_gone(404, GEMINI_RETIRED_BODY) is True


def test_retired_for_new_users_is_recognised():
    body = '{"error":{"message":"This model is no longer available to new users"}}'
    assert llm._is_model_gone(404, body) is True


def test_openai_model_not_found_code_is_recognised():
    body = '{"error": {"code": "model_not_found", "message": "The model does not exist"}}'
    assert llm._is_model_gone(404, body) is True


def test_generic_404_is_not_mistaken_for_a_dead_model():
    """A mistyped base URL also 404s. Swapping the model would be a non-fix, so
    a 404 that says nothing about a model must not trigger a switch."""
    assert llm._is_model_gone(404, "<html><h1>404 Not Found</h1></html>") is False


def test_server_error_is_not_a_dead_model():
    assert llm._is_model_gone(503, "upstream unavailable") is False


# --------------------------------------------------------------------------- #
# Choosing the replacement
# --------------------------------------------------------------------------- #
def test_prefers_a_ranked_fallback_that_is_actually_offered():
    picked = llm_config.pick_replacement_model(
        "gemini",
        ["gemini-2.0-flash", "gemini-3.6-flash", "gemini-flash-latest"],
        current="gemini-3-pro-preview",
    )
    assert picked == "gemini-flash-latest"


def test_never_returns_the_model_it_is_replacing():
    picked = llm_config.pick_replacement_model(
        "gemini", ["gemini-3-pro-preview"], current="gemini-3-pro-preview"
    )
    assert picked != "gemini-3-pro-preview"


def test_skips_models_built_for_another_modality():
    """The static list will itself go stale one day, so the heuristic path is the
    one that has to keep working: never hand categorization an image/TTS model."""
    picked = llm_config.pick_replacement_model(
        "gemini",
        ["gemini-9.9-flash-image", "gemini-9.9-flash-tts", "gemini-9.9-flash"],
        current="gemini-3-pro-preview",
    )
    assert picked == "gemini-9.9-flash"


def test_prefers_newer_unknown_flash_over_older_one():
    picked = llm_config.pick_replacement_model(
        "gemini", ["gemini-7.1-flash", "gemini-9.4-flash"], current="old"
    )
    assert picked == "gemini-9.4-flash"


def test_falls_back_blind_when_the_catalogue_is_unreachable():
    assert llm_config.pick_replacement_model("gemini", [], current="dead") is not None


# --------------------------------------------------------------------------- #
# Repairing the config
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_guard_switches_model_and_records_a_notice(conn, monkeypatch):
    repo.set_setting(conn, llm_config.K_PROVIDER, "gemini")
    repo.set_setting(conn, llm_config.K_MODEL, "gemini-3-pro-preview")
    monkeypatch.setattr(llm_config, "get_key", lambda c, p: "test-key")

    async def fake_check(config):
        if config.model == "gemini-3-pro-preview":
            return llm.HealthResult(False, None, "retired", model_gone=True)
        return llm.HealthResult(True, 4.0)

    async def fake_list(config):
        return ["gemini-3-pro-preview", "gemini-3.6-flash"]

    monkeypatch.setattr(llm, "check", fake_check)
    monkeypatch.setattr(llm, "list_models", fake_list)

    result = await model_guard.ensure_usable_model(conn)

    assert result.switched is True
    assert result.health.available is True
    assert result.config.model != "gemini-3-pro-preview"
    # Persisted, so the next launch doesn't repeat the discovery.
    assert repo.get_setting(conn, llm_config.K_MODEL) == result.config.model
    notice = llm_config.get_model_notice(conn)
    assert notice["previous_model"] == "gemini-3-pro-preview"
    assert notice["new_model"] == result.config.model


@pytest.mark.asyncio
async def test_guard_leaves_config_alone_when_nothing_works(conn, monkeypatch):
    """A failed repair must be a no-op, not a config left pointing somewhere
    arbitrary."""
    repo.set_setting(conn, llm_config.K_PROVIDER, "gemini")
    repo.set_setting(conn, llm_config.K_MODEL, "gemini-3-pro-preview")
    monkeypatch.setattr(llm_config, "get_key", lambda c, p: "test-key")

    async def all_gone(config):
        return llm.HealthResult(False, None, "retired", model_gone=True)

    async def fake_list(config):
        return ["gemini-3.6-flash", "gemini-2.5-flash"]

    monkeypatch.setattr(llm, "check", all_gone)
    monkeypatch.setattr(llm, "list_models", fake_list)

    result = await model_guard.ensure_usable_model(conn)

    assert result.switched is False
    assert repo.get_setting(conn, llm_config.K_MODEL) == "gemini-3-pro-preview"
    assert llm_config.get_model_notice(conn) is None


@pytest.mark.asyncio
async def test_guard_is_a_noop_for_a_healthy_model(conn, monkeypatch):
    repo.set_setting(conn, llm_config.K_PROVIDER, "gemini")
    repo.set_setting(conn, llm_config.K_MODEL, "gemini-3.6-flash")
    monkeypatch.setattr(llm_config, "get_key", lambda c, p: "test-key")

    async def healthy(config):
        return llm.HealthResult(True, 3.0)

    async def must_not_list(config):
        raise AssertionError("a working model must not trigger catalogue lookups")

    monkeypatch.setattr(llm, "check", healthy)
    monkeypatch.setattr(llm, "list_models", must_not_list)

    result = await model_guard.ensure_usable_model(conn)
    assert result.switched is False
    assert result.config.model == "gemini-3.6-flash"


# --------------------------------------------------------------------------- #
# Sync keeps going
# --------------------------------------------------------------------------- #
def _add_uncategorized(conn, raw, i):
    uncat = repo.upsert_category(conn, "Uncategorized", "#64748B")
    repo.insert_transaction(
        conn,
        {
            "date": "2026-01-01",
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
async def test_sync_categorizes_despite_a_retired_model(conn, monkeypatch):
    """The headline behaviour: the run completes instead of reporting a 404."""
    _add_uncategorized(conn, "AMZN MKTP US", 0)
    repo.set_setting(conn, llm_config.K_PROVIDER, "gemini")
    repo.set_setting(conn, llm_config.K_MODEL, "gemini-3-pro-preview")
    monkeypatch.setattr(llm_config, "get_key", lambda c, p: "test-key")

    async def fake_check(config):
        if config.model == "gemini-3-pro-preview":
            return llm.HealthResult(False, None, "retired", model_gone=True)
        return llm.HealthResult(True, 4.0)

    async def fake_list(config):
        return ["gemini-3.6-flash"]

    async def fake_batch(config, raws, cats):
        assert config.model == "gemini-3.6-flash", "must run on the replacement"
        return [llm.CleanResult(clean_merchant="Amazon", category="Shopping")]

    monkeypatch.setattr(llm, "check", fake_check)
    monkeypatch.setattr(llm, "list_models", fake_list)
    monkeypatch.setattr(llm, "clean_merchants_batch", fake_batch)

    result = await sync.resync(conn)

    assert result.recategorized == 1
    assert result.still_uncategorized == 0
    assert result.llm_available is True
    assert result.model_switched["new_model"] == "gemini-3.6-flash"


# --------------------------------------------------------------------------- #
# Retry / backoff
# --------------------------------------------------------------------------- #
def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test/v1/x")
    response = httpx.Response(code, request=request, text="upstream hiccup")
    return httpx.HTTPStatusError("boom", request=request, response=response)


@pytest.mark.asyncio
async def test_transient_server_error_is_retried_then_succeeds(monkeypatch):
    """One 5xx used to be able to end a whole run: sync aborts after a few
    consecutive failed chunks, and over hundreds of chunks a blip is close to
    certain."""
    monkeypatch.setattr(llm, "_BASE_BACKOFF_SECONDS", 0.0)
    calls = {"n": 0}

    async def flaky(config, prompt, system):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _status_error(503)
        return '{"clean_merchant": "Amazon", "category": "Shopping"}'

    monkeypatch.setattr(llm, "_generate", flaky)
    out = await llm._generate_with_retry(_config(), "p", "s")
    assert "Amazon" in out
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retries_are_bounded(monkeypatch):
    monkeypatch.setattr(llm, "_BASE_BACKOFF_SECONDS", 0.0)
    calls = {"n": 0}

    async def always_down(config, prompt, system):
        calls["n"] += 1
        raise _status_error(500)

    monkeypatch.setattr(llm, "_generate", always_down)
    with pytest.raises(httpx.HTTPStatusError):
        await llm._generate_with_retry(_config(), "p", "s")
    assert calls["n"] == llm._MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_a_dead_model_fails_fast_without_retrying(monkeypatch):
    """Retrying a retired model id just burns quota — it fails the same way
    every time."""
    monkeypatch.setattr(llm, "_BASE_BACKOFF_SECONDS", 0.0)
    calls = {"n": 0}
    request = httpx.Request("POST", "https://example.test/x")

    async def gone(config, prompt, system):
        calls["n"] += 1
        raise httpx.HTTPStatusError(
            "gone",
            request=request,
            response=httpx.Response(404, request=request, text=GEMINI_RETIRED_BODY),
        )

    monkeypatch.setattr(llm, "_generate", gone)
    with pytest.raises(httpx.HTTPStatusError):
        await llm._generate_with_retry(_config(), "p", "s")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_batch_surfaces_a_dead_model_as_model_unavailable(monkeypatch):
    monkeypatch.setattr(llm, "_BASE_BACKOFF_SECONDS", 0.0)
    request = httpx.Request("POST", "https://example.test/x")

    async def gone(config, prompt, system):
        raise httpx.HTTPStatusError(
            "gone",
            request=request,
            response=httpx.Response(404, request=request, text=GEMINI_RETIRED_BODY),
        )

    monkeypatch.setattr(llm, "_generate", gone)
    with pytest.raises(llm.ModelUnavailable):
        await llm.clean_merchants_batch(_config(), ["AMZN"], ["Shopping"])


def test_model_unavailable_still_degrades_gracefully():
    """Existing handlers catch LLMUnavailable; the new type must stay inside it
    so a provider that can't be repaired still degrades instead of crashing."""
    assert issubclass(llm.ModelUnavailable, llm.LLMUnavailable)


# --------------------------------------------------------------------------- #
# Log redaction — the log file is only shareable if it holds no secrets
# --------------------------------------------------------------------------- #
def test_access_log_query_string_key_is_redacted():
    """uvicorn formats the request path through record.args, which is exactly
    where a Gemini key would land. Redacting only record.msg would miss it."""
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s" %d',
        args=("127.0.0.1", "POST /models/x:generateContent?key=AIzaSuperSecret123", 200),
        exc_info=None,
    )
    assert logging_setup.RedactFilter().filter(record) is True
    rendered = record.getMessage()
    assert "AIzaSuperSecret123" not in rendered
    assert "REDACTED" in rendered


def test_bearer_token_is_redacted():
    assert "sk-abcdefghijklmnop" not in logging_setup.redact(
        "Authorization: Bearer sk-abcdefghijklmnop"
    )
