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
    ChangeEvent,
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
        "SELECT amount, substr(date, 1, 7) AS ym FROM transactions "
        "WHERE is_split_parent = 0"
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


def _effective_flow(
    base: float, events: list[ChangeEvent], kind: str, month: int
) -> float:
    """Apply income/expense change events (E2) cumulatively through `month`.

    Events are applied in month order: ``set`` replaces the running value with
    an absolute level; ``delta`` adds (or subtracts) from it. Only events whose
    effective month has arrived (``event.month <= month``) count.
    """
    value = base
    for e in sorted(
        (e for e in events if e.kind == kind), key=lambda e: e.month
    ):
        if e.month <= month:
            value = e.amount if e.mode == "set" else value + e.amount
    return value


def run_simulation(
    params: SimulationParameters,
    milestones: list[Milestone],
    events: list[ChangeEvent] | None = None,
) -> SimulationSeries:
    """Execute the discrete simulation and return runway + macro series."""
    events = events or []
    adj = 1.0 + (params.income_adjustment_pct / 100.0)
    base_inflow = params.monthly_inflow or 0.0
    base_outflow = params.monthly_outflow or 0.0

    def flows(month: int) -> tuple[float, float]:
        inflow = _effective_flow(base_inflow, events, "income", month) * adj
        outflow = _effective_flow(base_outflow, events, "expense", month)
        return inflow, outflow

    # --- Tactical runway ------------------------------------------------- #
    runway: list[RunwayPoint] = []
    cash = params.starting_cash
    failure_month: int | None = None
    for t in range(params.runway_months + 1):
        milestone_cost = _monthly_milestone_costs(milestones, t)
        # t=0 is the starting snapshot; flows begin accruing from t=1.
        if t > 0:
            inflow, outflow = flows(t)
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
    # into (a) asset value and (b) structural debt that amortizes (E1).
    monthly_return = (1.0 + params.annual_return_pct / 100.0) ** (1 / 12) - 1
    monthly_debt_rate = (1.0 + params.annual_debt_rate_pct / 100.0) ** (1 / 12) - 1
    monthly_inflation = (1.0 + params.annual_inflation_pct / 100.0) ** (1 / 12) - 1
    total_months = params.macro_years * 12

    assets = params.starting_assets
    structural_debt = params.starting_debt
    # Each amortizing loan tracks its own balance, monthly rate, payment, term.
    loans: list[dict] = []
    macro: list[MacroPoint] = []
    for t in range(total_months + 1):
        if t > 0:
            assets *= 1.0 + monthly_return
            structural_debt *= 1.0 + monthly_debt_rate
            inflow, outflow = flows(t)
            assets += max(inflow - outflow, 0.0)
            for m in milestones:
                if t == m.target_month:
                    assets += m.asset_value
                    if m.debt_incurred > 0:
                        rate_pct = (
                            m.apr if m.apr is not None else params.annual_debt_rate_pct
                        )
                        loans.append(
                            {
                                "balance": m.debt_incurred,
                                "rate": (1.0 + rate_pct / 100.0) ** (1 / 12) - 1,
                                "payment": m.recurring_payment,
                                "end": m.target_month + m.recurring_months,
                            }
                        )
            # Amortize each loan: interest accrues, the payment retires principal.
            for loan in loans:
                if loan["balance"] <= 0:
                    continue
                interest = loan["balance"] * loan["rate"]
                if t < loan["end"] and loan["payment"] > 0:
                    paid = max(0.0, loan["payment"] - interest)
                    loan["balance"] -= min(loan["balance"], paid)
                else:
                    # Past term (or no payment): unpaid balance keeps accruing.
                    loan["balance"] += interest
        if t % 12 == 0:
            debt = structural_debt + sum(loan["balance"] for loan in loans)
            net = assets - debt
            deflator = (1.0 + monthly_inflation) ** t if monthly_inflation else 1.0
            macro.append(
                MacroPoint(
                    year=t / 12,
                    total_assets=round(assets, 2),
                    remaining_debt=round(debt, 2),
                    net_worth=round(net, 2),
                    real_net_worth=round(net / deflator, 2),
                )
            )

    return SimulationSeries(
        runway=runway,
        macro=macro,
        failure_month=failure_month,
        safety_floor=params.safety_floor,
    )


def checkpoint_values(
    series: SimulationSeries, month: int
) -> tuple[float | None, float | None]:
    """Return (runway cash, macro net worth) at a checkpoint month.

    Cash is taken from the runway series when the month is within its horizon;
    net worth from the macro series when the month lands on a sampled year.
    Either can be ``None`` when the horizon does not reach that far.
    """
    cash = series.runway[month].cash if month < len(series.runway) else None
    net_worth = None
    if month % 12 == 0:
        year = month // 12
        if year < len(series.macro):
            net_worth = series.macro[year].net_worth
    return cash, net_worth


def evaluate_goal(
    series: SimulationSeries, kind: str, target_amount: float, target_month: int
) -> tuple[float | None, bool]:
    """Return (projected value, on_track) for a goal against a scenario series.

    ``on_track`` means the scenario reaches at least the target by the target
    month. Cash goals read the runway; net-worth goals read the macro series at
    the nearest sampled year at or before the target month.
    """
    if kind == "cash":
        idx = min(target_month, len(series.runway) - 1)
        projected: float | None = series.runway[idx].cash if series.runway else None
    else:  # net_worth
        year = min(target_month // 12, len(series.macro) - 1)
        projected = series.macro[year].net_worth if series.macro else None
    on_track = projected is not None and projected >= target_amount
    return projected, on_track


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
