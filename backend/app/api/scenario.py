"""Natural-language scenario endpoint."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import get_db
from app.models.schemas import ScenarioParseRequest, ScenarioParseResult
from app.services import scenario_parser

router = APIRouter(tags=["scenario"])


@router.post("/scenario/parse", response_model=ScenarioParseResult)
async def parse_scenario(
    body: ScenarioParseRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> ScenarioParseResult:
    """Turn a plain-English "what-if" into milestones + parameter overrides."""
    try:
        return await scenario_parser.parse_scenario(conn, body.text)
    except scenario_parser.ScenarioParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
