"""Local LLM health + provider configuration endpoints (PRD 4.1)."""
from __future__ import annotations

import logging
import sqlite3
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import get_db
from app.models.schemas import (
    LLMConfigIn,
    LLMConfigOut,
    LLMModelsResult,
    LLMStatus,
    LLMTestResult,
    ModelNotice,
    ProviderInfo,
)
from app.services import llm, llm_config, model_guard
from app.services.llm_config import PROVIDERS, LLMConfig

log = logging.getLogger("draftfi.api.llm")

router = APIRouter(prefix="/llm", tags=["llm"])

# The status pill polls this endpoint continuously, and the check is now a real
# (if tiny) generation against the configured model — the only thing that
# actually proves the setup works. That makes each check count against the
# user's quota, so cache the verdict for longer than the UI's poll interval.
# Any config change calls _invalidate_health_cache(), so the pill still reacts
# immediately to something the user did.
_HEALTH_TTL_SECONDS = 300.0
_health_cache: dict[tuple, tuple[float, LLMStatus]] = {}


def _invalidate_health_cache() -> None:
    _health_cache.clear()


def _endpoint(url: str) -> tuple[str, str]:
    """(scheme, host:port) — what actually decides where bytes are sent."""
    parsed = urlparse(url)
    return parsed.scheme.lower(), parsed.netloc.lower()


def _validate_base_url(url: str) -> None:
    """Reject anything that isn't a plausible provider endpoint.

    base_url arrives as a free-text field and ends up as the host we POST the
    user's API key to. Plain http is allowed only to loopback, because that is
    Ollama and LM Studio; everything else has to be https.
    """
    scheme, netloc = _endpoint(url)
    if scheme not in ("http", "https") or not netloc:
        raise HTTPException(
            status_code=400, detail="Base URL must be an http(s) address."
        )
    host = netloc.split(":")[0]
    if scheme == "http" and host not in ("127.0.0.1", "localhost", "::1", "[::1]"):
        raise HTTPException(
            status_code=400,
            detail="Only https endpoints are allowed (http is permitted for "
            "localhost, for Ollama and LM Studio).",
        )


def _transient_config(conn: sqlite3.Connection, body: LLMConfigIn) -> LLMConfig:
    """Build an unsaved config from form values.

    The stored key is reused ONLY when the request points at the same endpoint
    it was saved for. It used to be attached to whatever base_url the caller
    supplied, so a request naming any host — no key in the body at all — made
    the app read the secret out of the OS keychain and send it there. The
    keychain integration exists precisely so that key is not readable from
    disk; handing it out over an unauthenticated loopback call defeated it.
    """
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown provider.")
    spec = PROVIDERS[body.provider]
    base_url = (body.base_url or "").strip() or spec.default_base_url
    _validate_base_url(base_url)

    typed = (body.api_key or "").strip()
    api_key = typed
    if not api_key:
        saved = llm_config.resolve_config(conn)
        known = {_endpoint(spec.default_base_url)}
        if saved.provider == body.provider and saved.base_url:
            known.add(_endpoint(saved.base_url))
        if _endpoint(base_url) in known:
            api_key = llm_config.get_key(conn, body.provider) or ""
        else:
            log.warning(
                "Not sending the stored %s key to an unrecognised endpoint (%s); "
                "the user must re-enter it to test a custom host.",
                body.provider,
                base_url,
            )

    return LLMConfig(
        provider=body.provider,
        model=(body.model or "").strip() or spec.default_model,
        base_url=base_url,
        api_key=api_key or None,
    )


def _notice_model(raw: dict | None) -> ModelNotice | None:
    if not raw:
        return None
    try:
        return ModelNotice(**raw)
    except (TypeError, ValueError):  # pragma: no cover - malformed stored row
        return None


@router.get("/status", response_model=LLMStatus)
async def llm_status(conn: sqlite3.Connection = Depends(get_db)) -> LLMStatus:
    config = llm_config.resolve_config(conn)

    # A pending OS keychain prompt means the key genuinely isn't readable yet.
    # Say so, rather than probing the provider without a key and reporting the
    # misleading "no API key configured" — and don't cache a state the user is
    # about to resolve with one click.
    keychain = llm_config.keychain_status()
    if keychain == llm_config.KEYCHAIN_WAITING and not config.api_key:
        return LLMStatus(
            available=False,
            latency_ms=None,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            detail=(
                "Waiting for keychain approval — your OS is asking permission "
                "to read the saved API key. Approve the prompt (choose Always "
                "Allow) and this clears itself."
            ),
            notice=_notice_model(llm_config.get_model_notice(conn)),
            keychain=keychain,
        )

    key = (config.provider, config.model, config.base_url)
    cached = _health_cache.get(key)
    if cached and (time.monotonic() - cached[0]) < _HEALTH_TTL_SECONDS:
        # Re-read the notice so dismissing it takes effect without waiting out
        # the health TTL.
        return cached[1].model_copy(
            update={"notice": _notice_model(llm_config.get_model_notice(conn))}
        )

    # A retired model is repaired here rather than reported: the user gets a
    # working provider and a note about what changed, not a red pill and a
    # 404 they can do nothing with.
    guard = await model_guard.ensure_usable_model(conn, config)
    if guard.switched:
        _invalidate_health_cache()
    config, result = guard.config, guard.health

    status = LLMStatus(
        available=result.available,
        latency_ms=result.latency_ms,
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        detail=result.detail,
        notice=_notice_model(llm_config.get_model_notice(conn)),
        keychain=llm_config.keychain_status(),
    )
    if status.keychain != llm_config.KEYCHAIN_WAITING:
        _health_cache[(config.provider, config.model, config.base_url)] = (
            time.monotonic(),
            status,
        )
    return status


@router.post("/notice/dismiss", response_model=LLMStatus)
async def dismiss_notice(conn: sqlite3.Connection = Depends(get_db)) -> LLMStatus:
    """Clear the "we switched your model" note once the user has seen it."""
    llm_config.clear_model_notice(conn)
    conn.commit()
    return await llm_status(conn)


def _config_out(conn: sqlite3.Connection) -> LLMConfigOut:
    config = llm_config.resolve_config(conn)
    providers = [
        ProviderInfo(
            id=spec.id,
            label=spec.label,
            requires_key=spec.requires_key,
            is_local=spec.is_local,
            default_model=spec.default_model,
            default_base_url=spec.default_base_url,
            model_hint=spec.model_hint,
            has_key=llm_config.has_key(conn, spec.id),
        )
        for spec in llm_config.PROVIDERS.values()
    ]
    return LLMConfigOut(
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        providers=providers,
    )


@router.post("/test", response_model=LLMTestResult)
async def test_connection(
    body: LLMConfigIn,
    conn: sqlite3.Connection = Depends(get_db),
) -> LLMTestResult:
    """A1: validate the pasted key/endpoint on demand, without saving."""
    config = _transient_config(conn, body)
    result = await llm.check(config)
    suggestion: str | None = None
    if result.model_gone:
        # Don't just say no — the user is standing right there, so tell them
        # which model to pick instead.
        try:
            available = await llm.list_models(config)
        except llm.LLMError:
            available = []
        suggestion = llm_config.pick_replacement_model(
            config.provider, available, current=config.model
        )
    return LLMTestResult(
        ok=result.available,
        latency_ms=result.latency_ms,
        detail=result.detail,
        model_gone=result.model_gone,
        suggested_model=suggestion,
    )


@router.post("/models", response_model=LLMModelsResult)
async def list_models(
    body: LLMConfigIn,
    conn: sqlite3.Connection = Depends(get_db),
) -> LLMModelsResult:
    """A2: fetch the provider's live model list (client falls back to free text).

    ``recommended`` marks the model DraftFi would pick for categorization, so
    the picker can flag a sensible default instead of an alphabetical list.
    """
    config = _transient_config(conn, body)
    try:
        models = await llm.list_models(config)
    except llm.LLMError as exc:
        return LLMModelsResult(models=[], detail=str(exc))
    return LLMModelsResult(
        models=models,
        recommended=llm_config.pick_replacement_model(config.provider, models),
    )


@router.get("/config", response_model=LLMConfigOut)
def get_config(conn: sqlite3.Connection = Depends(get_db)) -> LLMConfigOut:
    """Return active provider + per-provider metadata.

    The stored API key is never returned — only a ``has_key`` flag per provider.
    """
    return _config_out(conn)


@router.put("/config", response_model=LLMConfigOut)
def put_config(
    body: LLMConfigIn,
    conn: sqlite3.Connection = Depends(get_db),
) -> LLMConfigOut:
    """Set active provider/model/base URL and optionally store an API key."""
    # Same check as the transient path. A persisted base_url is worse than a
    # one-off: it redirects every future categorization call — key and merchant
    # text — for good.
    if (body.base_url or "").strip():
        _validate_base_url(body.base_url.strip())
    try:
        llm_config.save_config(
            conn,
            provider=body.provider,
            model=body.model,
            base_url=body.base_url,
            api_key=body.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # An explicit choice supersedes any automatic switch we made earlier.
    llm_config.clear_model_notice(conn)
    conn.commit()
    _invalidate_health_cache()
    return _config_out(conn)


@router.delete("/config/{provider}/key", response_model=LLMConfigOut)
def delete_key(
    provider: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> LLMConfigOut:
    """Remove a stored API key for a provider."""
    if provider not in llm_config.PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider.")
    llm_config.clear_key(conn, provider)
    conn.commit()
    _invalidate_health_cache()
    return _config_out(conn)
