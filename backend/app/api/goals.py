"""Goal tracking endpoints (E5) — target net worth / cash by a future month.

Goals are plain records; whether each is on-track is evaluated on the frontend
against the active scenario's already-computed simulation series, so changing a
slider re-evaluates instantly without a round-trip.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import repository as repo
from app.db.connection import get_db
from app.models.schemas import Goal, GoalCreate, GoalUpdate

router = APIRouter(tags=["goals"])


@router.get("/goals", response_model=list[Goal])
def list_goals(conn: sqlite3.Connection = Depends(get_db)) -> list[Goal]:
    return [Goal(**g) for g in repo.list_goals(conn)]


@router.post("/goals", response_model=Goal, status_code=201)
def create_goal(
    body: GoalCreate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Goal:
    goal_id = repo.create_goal(
        conn,
        label=body.label,
        kind=body.kind,
        target_amount=body.target_amount,
        target_month=body.target_month,
    )
    conn.commit()
    created = repo.get_goal(conn, goal_id)
    assert created is not None
    return Goal(**created)


@router.patch("/goals/{goal_id}", response_model=Goal)
def update_goal(
    goal_id: int,
    body: GoalUpdate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Goal:
    if repo.get_goal(conn, goal_id) is None:
        raise HTTPException(status_code=404, detail="Goal not found.")
    repo.update_goal(
        conn,
        goal_id,
        label=body.label,
        kind=body.kind,
        target_amount=body.target_amount,
        target_month=body.target_month,
    )
    conn.commit()
    updated = repo.get_goal(conn, goal_id)
    assert updated is not None
    return Goal(**updated)


@router.delete("/goals/{goal_id}", status_code=204, response_class=Response)
def delete_goal(
    goal_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    if repo.get_goal(conn, goal_id) is None:
        raise HTTPException(status_code=404, detail="Goal not found.")
    repo.delete_goal(conn, goal_id)
    conn.commit()
    return Response(status_code=204)
