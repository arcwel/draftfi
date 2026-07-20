"""Subscriptions (A3) + monthly insights (A4) endpoints.

Both the recurring-charge detection and the heuristic insights are deterministic
and provider-free. The optional LLM narrative is a separate, on-demand call so
the default views never wait on (or require) a model.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import get_db
from app.models.schemas import (
    InsightsList,
    NarrativeResult,
    SubscriptionsSummary,
)
from app.services import insights as insights_svc
from app.services import llm, llm_config, subscriptions

router = APIRouter(tags=["insights"])


@router.get("/subscriptions", response_model=SubscriptionsSummary)
def get_subscriptions(
    conn: sqlite3.Connection = Depends(get_db),
) -> SubscriptionsSummary:
    """A3: detected recurring charges + total active monthly cost."""
    return SubscriptionsSummary(**subscriptions.detect_subscriptions(conn))


@router.get("/insights", response_model=InsightsList)
def get_insights(conn: sqlite3.Connection = Depends(get_db)) -> InsightsList:
    """A4: heuristic month-over-month insights (always available)."""
    return InsightsList(insights=insights_svc.compute_insights(conn))


@router.post("/insights/narrative", response_model=NarrativeResult)
async def get_narrative(
    conn: sqlite3.Connection = Depends(get_db),
) -> NarrativeResult:
    """A4: opt-in LLM narrative of the current insights (needs a live provider)."""
    config = llm_config.resolve_config(conn)
    facts = insights_svc.compute_insights(conn)
    try:
        narrative = await insights_svc.generate_narrative(config, facts)
    except llm.LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return NarrativeResult(narrative=narrative)
