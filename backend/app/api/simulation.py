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
    ChangeEvent,
    CompareRequest,
    CompareResult,
    DeltaCell,
    DeltaRow,
    Milestone,
    MultiCompareResult,
    ScenarioSeries,
    SimulationParameters,
    SimulationRequest,
    SimulationSeries,
)
from app.services import simulation

router = APIRouter(tags=["simulation"])

# Fixed horizons for the multi-branch delta table (E4).
COMPARE_CHECKPOINTS = [12, 36, 72]


def _branch_to_model(row: dict) -> Branch:
    return Branch(
        id=row["id"],
        name=row["name"],
        is_base=row["is_base"],
        parameters=SimulationParameters(**(row["parameters"] or {})),
        milestones=row["milestones"] or [],
        events=row.get("events") or [],
    )


def _simulate_branch(conn: sqlite3.Connection, row: dict) -> SimulationSeries:
    """Resolve a stored branch row into a full simulation series."""
    params = simulation.resolve_parameters(
        conn, SimulationParameters(**(row["parameters"] or {}))
    )
    milestones = [Milestone(**m) for m in (row["milestones"] or [])]
    events = [ChangeEvent(**e) for e in (row.get("events") or [])]
    return simulation.run_simulation(params, milestones, events)


@router.post("/simulate", response_model=SimulationSeries)
def simulate(
    req: SimulationRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> SimulationSeries:
    """Run a one-off simulation (baselines auto-derived when unset)."""
    params = simulation.resolve_parameters(conn, req.parameters)
    return simulation.run_simulation(params, req.milestones, req.events)


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
        events=source.get("events") or [],
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
        events=[e.model_dump() for e in body.events]
        if body.events is not None
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

    return CompareResult(
        base=_simulate_branch(conn, base),
        branch=_simulate_branch(conn, branch),
        base_branch_id=base["id"],
        branch_id=branch["id"],
    )


@router.post("/scenarios/compare", response_model=MultiCompareResult)
def compare_scenarios(
    body: CompareRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> MultiCompareResult:
    """Overlay the Base Plan plus any selected branches, with a delta table (E4).

    The Base Plan always anchors the comparison; the delta columns are measured
    against it at fixed horizons (12/36/72 months).
    """
    base = repo.get_base_branch(conn)
    if base is None:
        raise HTTPException(status_code=404, detail="Base Plan not found.")

    # Base first, then each requested branch (skipping the base / unknown ids).
    rows = [base]
    for bid in body.branch_ids:
        if bid == base["id"]:
            continue
        row = repo.get_branch(conn, bid)
        if row is not None:
            rows.append(row)

    scenarios = [
        ScenarioSeries(
            branch_id=row["id"],
            name=row["name"],
            is_base=row["is_base"],
            series=_simulate_branch(conn, row),
        )
        for row in rows
    ]

    base_scenario = scenarios[0]
    deltas: list[DeltaRow] = []
    for month in COMPARE_CHECKPOINTS:
        base_cash, base_net = simulation.checkpoint_values(base_scenario.series, month)
        cells: list[DeltaCell] = []
        for sc in scenarios:
            cash, net = simulation.checkpoint_values(sc.series, month)
            cells.append(
                DeltaCell(
                    branch_id=sc.branch_id,
                    name=sc.name,
                    is_base=sc.is_base,
                    cash=cash,
                    net_worth=net,
                    cash_delta=None
                    if sc.is_base or cash is None or base_cash is None
                    else round(cash - base_cash, 2),
                    net_delta=None
                    if sc.is_base or net is None or base_net is None
                    else round(net - base_net, 2),
                )
            )
        deltas.append(DeltaRow(month=month, cells=cells))

    return MultiCompareResult(
        scenarios=scenarios, checkpoints=COMPARE_CHECKPOINTS, deltas=deltas
    )
