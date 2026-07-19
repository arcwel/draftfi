"""Budget analytics: monthly spending by category + scenario impact.

Turns the transaction history into an at-a-glance monthly budget, then layers
on how the active scenario (income adjustment + milestones) shifts it. This is
the "what does my money actually do each month, and what happens if I…" view.

* Per-category monthly averages come from real transactions, normalized by the
  number of distinct calendar months observed so one fat statement doesn't
  inflate the monthly rate.
* Scenario impact reuses the same assumptions the simulation engine uses:
  income scales by the −30%…+30% slider; milestone recurring payments add a
  monthly commitment during their active window; down payments are one-time.
"""
from __future__ import annotations

import sqlite3

from app.db import repository as repo
from app.models.schemas import (
    BudgetCategory,
    BudgetSummary,
    CashflowPoint,
    CategorySeriesPoint,
    CategoryTrend,
    MilestoneImpact,
    ScenarioBudgetImpact,
    SimulationParameters,
    TrendsSummary,
)
from app.models.schemas import Milestone as MilestoneModel

# Categories treated as income rather than spend when splitting the budget.
INCOME_CATEGORY_NAMES = {"income", "savings & investments"}


def _is_income(name: str, total: float) -> bool:
    return name.strip().lower() in INCOME_CATEGORY_NAMES or total > 0


def _carried_over(
    conn: sqlite3.Connection, category_id: int, budget: float, upto_month: str
) -> float:
    """Unspent budget accumulated from months strictly before ``upto_month``.

    Only positive surplus carries; an over-spent month does not create debt.
    """
    rows = conn.execute(
        "SELECT substr(date,1,7) AS ym, SUM(amount) AS total FROM transactions "
        "WHERE is_split_parent = 0 AND category_id = ? AND substr(date,1,7) < ? "
        "GROUP BY ym",
        (category_id, upto_month),
    ).fetchall()
    carried = 0.0
    for r in rows:
        spent = abs(float(r["total"]))
        carried += max(0.0, budget - spent)
    return carried


def compute_budget(
    conn: sqlite3.Connection,
    params: SimulationParameters,
    milestones: list[MilestoneModel],
    month: str | None = None,
) -> BudgetSummary:
    """Monthly budget: all-time average, or a single YYYY-MM month when given."""
    available = repo.observed_months(conn)
    if month:
        rows = repo.category_breakdown_for_month(conn, month)
        divisor = 1  # a specific month is already a monthly figure
    else:
        rows = repo.category_breakdown(conn)
        divisor = repo.months_observed(conn)

    categories: list[BudgetCategory] = []
    total_income = 0.0
    total_expense = 0.0
    total_budget_target = 0.0
    any_target = False

    for r in rows:
        total = float(r["total"])
        income = _is_income(r["category_name"] or "", total)
        # Monthly magnitude, always presented as a positive number.
        monthly = abs(total) / divisor
        if income:
            total_income += monthly
        else:
            total_expense += monthly

        target = r["monthly_budget"]
        has_rollover_col = "budget_rollover" in r.keys()
        rollover = bool(r["budget_rollover"]) if has_rollover_col else False
        over = False
        used_pct: float | None = None
        carried: float | None = None
        effective: float | None = None
        if target is not None:
            any_target = True
            total_budget_target += float(target)
            effective_budget = float(target)
            # Rollover only applies when viewing a specific month.
            if rollover and month and r["category_id"] is not None:
                carried = round(
                    _carried_over(conn, int(r["category_id"]), float(target), month),
                    2,
                )
                effective_budget = float(target) + carried
                effective = round(effective_budget, 2)
            if effective_budget > 0:
                used_pct = round(monthly / effective_budget * 100.0, 1)
                over = monthly > effective_budget

        categories.append(
            BudgetCategory(
                category_id=r["category_id"],
                name=r["category_name"] or "Uncategorized",
                color=r["category_color"] or "#64748B",
                is_income=income,
                monthly_amount=round(monthly, 2),
                total=round(total, 2),
                transactions=int(r["n"]),
                monthly_budget=target,
                over_budget=over,
                budget_used_pct=used_pct,
                rollover=rollover,
                carried_over=carried,
                effective_budget=effective,
            )
        )

    # Manual overrides win: if the user typed a monthly income/spending, use it
    # for the headline totals (per-category bars still come from transactions).
    if params.monthly_inflow is not None:
        total_income = params.monthly_inflow
    if params.monthly_outflow is not None:
        total_expense = params.monthly_outflow

    scenario = _scenario_impact(
        params, milestones, total_income, total_expense
    )

    return BudgetSummary(
        months_observed=repo.months_observed(conn),
        categories=categories,
        total_monthly_income=round(total_income, 2),
        total_monthly_expense=round(total_expense, 2),
        total_monthly_net=round(total_income - total_expense, 2),
        total_budget_target=round(total_budget_target, 2),
        budget_target_set=any_target,
        scenario=scenario,
        month=month,
        available_months=available,
    )


def compute_trends(conn: sqlite3.Connection) -> TrendsSummary:
    """Month-over-month cash flow and per-category series for trend charts."""
    months = repo.observed_months(conn)
    rows = repo.monthly_series(conn)

    # Aggregate per-month cash flow and per-category series.
    cash: dict[str, dict[str, float]] = {
        m: {"income": 0.0, "expense": 0.0} for m in months
    }
    cats: dict[int | None, dict] = {}
    for r in rows:
        ym = r["ym"]
        total = float(r["total"])
        income = _is_income(r["category_name"] or "", total)
        magnitude = abs(total)
        if ym in cash:
            cash[ym]["income" if income else "expense"] += magnitude
        cid = r["category_id"]
        if cid not in cats:
            cats[cid] = {
                "category_id": cid,
                "name": r["category_name"] or "Uncategorized",
                "color": r["category_color"] or "#64748B",
                "is_income": income,
                "by_month": {},
            }
        cats[cid]["by_month"][ym] = round(magnitude, 2)

    cashflow = [
        CashflowPoint(
            month=m,
            income=round(cash[m]["income"], 2),
            expense=round(cash[m]["expense"], 2),
            net=round(cash[m]["income"] - cash[m]["expense"], 2),
        )
        for m in months
    ]
    categories = [
        CategoryTrend(
            category_id=c["category_id"],
            name=c["name"],
            color=c["color"],
            is_income=c["is_income"],
            series=[
                CategorySeriesPoint(month=m, amount=c["by_month"].get(m, 0.0))
                for m in months
            ],
        )
        for c in cats.values()
    ]
    return TrendsSummary(months=months, cashflow=cashflow, categories=categories)


def _scenario_impact(
    params: SimulationParameters,
    milestones: list[MilestoneModel],
    baseline_income: float,
    baseline_expense: float,
) -> ScenarioBudgetImpact:
    """How the active scenario reshapes the monthly budget.

    ``baseline_income``/``baseline_expense`` are derived from history unless the
    user overrode monthly inflow/outflow in the parameters, in which case those
    explicit values take precedence (they drive the simulation too).
    """
    if params.monthly_inflow is not None:
        baseline_income = params.monthly_inflow
    if params.monthly_outflow is not None:
        baseline_expense = params.monthly_outflow

    adj = params.income_adjustment_pct
    scenario_income = baseline_income * (1.0 + adj / 100.0)

    recurring_total = 0.0
    one_time_total = 0.0
    impacts: list[MilestoneImpact] = []
    for m in milestones:
        recurring = m.recurring_payment if m.recurring_months > 0 else 0.0
        recurring_total += recurring
        one_time_total += m.down_payment
        impacts.append(
            MilestoneImpact(
                label=m.label,
                monthly_amount=round(recurring, 2),
                start_month=m.target_month,
                end_month=m.target_month + max(0, m.recurring_months),
                one_time_cost=round(m.down_payment, 2),
            )
        )

    scenario_expense = baseline_expense + recurring_total
    baseline_net = baseline_income - baseline_expense
    scenario_net = scenario_income - scenario_expense

    return ScenarioBudgetImpact(
        income_adjustment_pct=adj,
        baseline_monthly_income=round(baseline_income, 2),
        scenario_monthly_income=round(scenario_income, 2),
        baseline_monthly_expense=round(baseline_expense, 2),
        scenario_monthly_expense=round(scenario_expense, 2),
        recurring_milestone_cost=round(recurring_total, 2),
        one_time_cost=round(one_time_total, 2),
        baseline_monthly_net=round(baseline_net, 2),
        scenario_monthly_net=round(scenario_net, 2),
        net_delta=round(scenario_net - baseline_net, 2),
        milestones=impacts,
    )
