"""Local LLM health + provider configuration endpoints (PRD 4.1)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import get_db
from app.models.schemas import (
    LLMConfigIn,
    LLMConfigOut,
    LLMModelsResult,
    LLMStatus,
    LLMTestResult,
    ProviderInfo,
)
from app.services import llm, llm_config
from app.services.llm_config import PROVIDERS, LLMConfig

router = APIRouter(prefix="/llm", tags=["llm"])


def _transient_config(conn: sqlite3.Connection, body: LLMConfigIn) -> LLMConfig:
    """Build an unsaved config from form values, reusing the stored key when the
    user hasn't re-typed one (so Test/model-fetch work against a saved secret)."""
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown provider.")
    spec = PROVIDERS[body.provider]
    typed = (body.api_key or "").strip()
    return LLMConfig(
        provider=body.provider,
        model=(body.model or "").strip() or spec.default_model,
        base_url=(body.base_url or "").strip() or spec.default_base_url,
        api_key=typed or llm_config.get_key(conn, body.provider),
    )


@router.get("/status", response_model=LLMStatus)
async def llm_status(conn: sqlite3.Connection = Depends(get_db)) -> LLMStatus:
    config = llm_config.resolve_config(conn)
    available, latency_ms, detail = await llm.health(config)
    return LLMStatus(
        available=available,
        latency_ms=latency_ms,
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        detail=detail,
    )


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
    ok, latency_ms, detail = await llm.health(config)
    return LLMTestResult(ok=ok, latency_ms=latency_ms, detail=detail)


@router.post("/models", response_model=LLMModelsResult)
async def list_models(
    body: LLMConfigIn,
    conn: sqlite3.Connection = Depends(get_db),
) -> LLMModelsResult:
    """A2: fetch the provider's live model list (client falls back to free text)."""
    config = _transient_config(conn, body)
    try:
        models = await llm.list_models(config)
    except llm.LLMError as exc:
        return LLMModelsResult(models=[], detail=str(exc))
    return LLMModelsResult(models=models)


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
    conn.commit()
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
    return _config_out(conn)
