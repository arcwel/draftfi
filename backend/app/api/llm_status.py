"""Local LLM health + provider configuration endpoints (PRD 4.1)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import get_db
from app.models.schemas import (
    LLMConfigIn,
    LLMConfigOut,
    LLMStatus,
    ProviderInfo,
)
from app.services import llm, llm_config

router = APIRouter(prefix="/llm", tags=["llm"])


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
