"""Discrete monthly financial simulation engine (PRD 7).

Two outputs from one pass:

* **Tactical runway** — month-by-month combined liquid cash over 12-72 months,
  driven by the discrete recurrence:

      Cash_Ending_t = Cash_Starting_t + Inflows_t - Outflows_t - Milestone_Costs_t

* **Macro wealth** — multi-year Total Assets vs. Remaining Structural Debt with
  compound growth and opportunity cost of deployed capital.

Pure functions, no I/O — cheap enough to hit the 150ms end-to-end budget with
room to spare (the whole thing is O(months)).
"""
from __future__ import annotations

import sqlite3

from app.models.schemas import (
    MacroPoint,
    Milestone,
    RunwayPoint,
    SimulationParameters,
    SimulationSeries,
)


def derive_baseline(conn: sqlite3.Connection) -> tuple[float, float]:
    """Infer monthly (inflow, outflow) from historical transactions.

    Positive amounts are treated as inflows, negative as outflows. Totals are
    averaged across the number of distinct calendar months observed so a single
    large statement does not distort the monthly rate.
    """
    rows = conn.execute(
        "SELECT amount, substr(date, 1, 7) AS ym FROM transactions"
    ).fetchall()
    if not rows:
        return 0.0, 0.0
    months = {r["ym"] for r in rows if r["ym"]} or {"one"}
    n_months = max(1, len(months))
    inflow = sum(r["amount"] for r in rows if r["amount"] > 0)
    outflow = sum(-r["amount"] for r in rows if r["amount"] < 0)
    return inflow / n_months, outflow / n_months


def _monthly_milestone_costs(milestones: list[Milestone], month: int) -> float:
    """Total cash outflow attributable to milestones in a given month index."""
    cost = 0.0
    for m in milestones:
        if month == m.target_month:
            cost += m.down_payment
        # Recurring payments run for `recurring_months` starting at target.
        if (
            m.recurring_payment
            and m.recurring_months > 0
            and m.target_month <= month < m.target_month + m.recurring_months
        ):
            cost += m.recurring_payment
    return cost


def run_simulation(
    params: SimulationParameters,
    milestones: list[Milestone],
) -> SimulationSeries:
    """Execute the discrete simulation and return runway + macro series."""
    adj = 1.0 + (params.income_adjustment_pct / 100.0)
    inflow = (params.monthly_inflow or 0.0) * adj
    outflow = params.monthly_outflow or 0.0

    # --- Tactical runway ------------------------------------------------- #
    runway: list[RunwayPoint] = []
    cash = params.starting_cash
    failure_month: int | None = None
    for t in range(params.runway_months + 1):
        milestone_cost = _monthly_milestone_costs(milestones, t)
        # t=0 is the starting snapshot; flows begin accruing from t=1.
        if t > 0:
            cash = cash + inflow - outflow - milestone_cost
        else:
            cash = cash - _monthly_milestone_costs(milestones, 0)
        below = cash < params.safety_floor
        if below and failure_month is None:
            failure_month = t
        runway.append(RunwayPoint(month=t, cash=round(cash, 2), below_floor=below))

    # --- Macro wealth ---------------------------------------------------- #
    # Monthly compounding of assets and debt over the long horizon. Surplus
    # cash flow is invested; milestone down payments convert liquid capital
    # into (a) asset value and (b) structural debt.
    monthly_return = (1.0 + params.annual_return_pct / 100.0) ** (1 / 12) - 1
    monthly_debt_rate = (1.0 + params.annual_debt_rate_pct / 100.0) ** (1 / 12) - 1
    total_months = params.macro_years * 12
    monthly_surplus = inflow - outflow

    assets = params.starting_assets
    debt = params.starting_debt
    macro: list[MacroPoint] = []
    for t in range(total_months + 1):
        if t > 0:
            assets *= 1.0 + monthly_return
            debt *= 1.0 + monthly_debt_rate
            assets += max(monthly_surplus, 0.0)
            for m in milestones:
                if t == m.target_month:
                    assets += m.asset_value
                    debt += m.debt_incurred
                if (
                    m.recurring_payment
                    and m.recurring_months > 0
                    and m.target_month <= t < m.target_month + m.recurring_months
                ):
                    # Recurring payments pay down structural debt first.
                    debt = max(0.0, debt - m.recurring_payment)
        if t % 12 == 0:
            macro.append(
                MacroPoint(
                    year=t / 12,
                    total_assets=round(assets, 2),
                    remaining_debt=round(debt, 2),
                    net_worth=round(assets - debt, 2),
                )
            )

    return SimulationSeries(
        runway=runway,
        macro=macro,
        failure_month=failure_month,
        safety_floor=params.safety_floor,
    )


def resolve_parameters(
    conn: sqlite3.Connection, params: SimulationParameters
) -> SimulationParameters:
    """Fill in missing inflow/outflow from historical data when not supplied."""
    if params.monthly_inflow is None or params.monthly_outflow is None:
        base_in, base_out = derive_baseline(conn)
        data = params.model_copy()
        if data.monthly_inflow is None:
            data.monthly_inflow = round(base_in, 2)
        if data.monthly_outflow is None:
            data.monthly_outflow = round(base_out, 2)
        return data
    return params
