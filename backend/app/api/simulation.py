"""Simulation + sandbox-branch endpoints (PRD 5, 6.2, 7)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import repository as repo
from app.db.connection import get_db
from app.models.schemas import (
    Branch,
    BranchCreate,
    BranchUpdate,
    CompareResult,
    SimulationParameters,
    SimulationRequest,
    SimulationSeries,
)
from app.services import simulation

router = APIRouter(tags=["simulation"])


def _branch_to_model(row: dict) -> Branch:
    return Branch(
        id=row["id"],
        name=row["name"],
        is_base=row["is_base"],
        parameters=SimulationParameters(**(row["parameters"] or {})),
        milestones=row["milestones"] or [],
    )


@router.post("/simulate", response_model=SimulationSeries)
def simulate(
    req: SimulationRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> SimulationSeries:
    """Run a one-off simulation (baselines auto-derived when unset)."""
    params = simulation.resolve_parameters(conn, req.parameters)
    return simulation.run_simulation(params, req.milestones)


# --------------------------------------------------------------------------- #
# Branches
# --------------------------------------------------------------------------- #
@router.get("/branches", response_model=list[Branch])
def list_branches(conn: sqlite3.Connection = Depends(get_db)) -> list[Branch]:
    return [_branch_to_model(b) for b in repo.list_branches(conn)]


@router.post("/branches", response_model=Branch, status_code=201)
def create_branch(
    body: BranchCreate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Branch:
    """Single-click branch duplication from a source (defaults to Base Plan)."""
    source = (
        repo.get_branch(conn, body.source_branch_id)
        if body.source_branch_id is not None
        else repo.get_base_branch(conn)
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source branch not found.")
    new_id = repo.create_branch(
        conn,
        name=body.name,
        parameters=source["parameters"],
        milestones=source["milestones"],
        is_base=False,
    )
    conn.commit()
    created = repo.get_branch(conn, new_id)
    assert created is not None
    return _branch_to_model(created)


@router.patch("/branches/{branch_id}", response_model=Branch)
def update_branch(
    branch_id: int,
    body: BranchUpdate,
    conn: sqlite3.Connection = Depends(get_db),
) -> Branch:
    """Update a plan's parameters/milestones.

    The Base Plan is editable — it represents your real financial baseline. It's
    protected only from deletion (see DELETE), and sandbox branches are
    independent copies, so experimenting in a branch never changes the base.
    """
    branch = repo.get_branch(conn, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found.")
    repo.update_branch(
        conn,
        branch_id,
        name=body.name,
        parameters=body.parameters.model_dump() if body.parameters else None,
        milestones=[m.model_dump() for m in body.milestones]
        if body.milestones is not None
        else None,
    )
    conn.commit()
    updated = repo.get_branch(conn, branch_id)
    assert updated is not None
    return _branch_to_model(updated)


@router.delete("/branches/{branch_id}", status_code=204, response_class=Response)
def delete_branch(
    branch_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    branch = repo.get_branch(conn, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found.")
    if branch["is_base"]:
        raise HTTPException(status_code=403, detail="Cannot delete the Base Plan.")
    repo.delete_branch(conn, branch_id)
    conn.commit()
    return Response(status_code=204)


@router.get("/branches/{branch_id}/compare", response_model=CompareResult)
def compare_branch(
    branch_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> CompareResult:
    """Return Base + Branch simulation series together for overlay mapping."""
    base = repo.get_base_branch(conn)
    branch = repo.get_branch(conn, branch_id)
    if base is None or branch is None:
        raise HTTPException(status_code=404, detail="Branch not found.")

    base_params = simulation.resolve_parameters(
        conn, SimulationParameters(**(base["parameters"] or {}))
    )
    branch_params = simulation.resolve_parameters(
        conn, SimulationParameters(**(branch["parameters"] or {}))
    )
    from app.models.schemas import Milestone

    base_series = simulation.run_simulation(
        base_params, [Milestone(**m) for m in base["milestones"]]
    )
    branch_series = simulation.run_simulation(
        branch_params, [Milestone(**m) for m in branch["milestones"]]
    )
    return CompareResult(
        base=base_series,
        branch=branch_series,
        base_branch_id=base["id"],
        branch_id=branch["id"],
    )
