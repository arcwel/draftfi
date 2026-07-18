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
    MilestoneImpact,
    ScenarioBudgetImpact,
    SimulationParameters,
)
from app.models.schemas import Milestone as MilestoneModel

# Categories treated as income rather than spend when splitting the budget.
INCOME_CATEGORY_NAMES = {"income", "savings & investments"}


def _is_income(name: str, total: float) -> bool:
    return name.strip().lower() in INCOME_CATEGORY_NAMES or total > 0


def compute_budget(
    conn: sqlite3.Connection,
    params: SimulationParameters,
    milestones: list[MilestoneModel],
) -> BudgetSummary:
    months = repo.months_observed(conn)
    rows = repo.category_breakdown(conn)

    categories: list[BudgetCategory] = []
    total_income = 0.0
    total_expense = 0.0
    total_budget_target = 0.0
    any_target = False

    for r in rows:
        total = float(r["total"])
        income = _is_income(r["category_name"] or "", total)
        # Monthly magnitude, always presented as a positive number.
        monthly = abs(total) / months
        if income:
            total_income += monthly
        else:
            total_expense += monthly

        target = r["monthly_budget"]
        over = False
        used_pct: float | None = None
        if target is not None:
            any_target = True
            total_budget_target += float(target)
            if target > 0:
                used_pct = round(monthly / float(target) * 100.0, 1)
                over = monthly > float(target)

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
            )
        )

    scenario = _scenario_impact(
        params, milestones, total_income, total_expense
    )

    return BudgetSummary(
        months_observed=months,
        categories=categories,
        total_monthly_income=round(total_income, 2),
        total_monthly_expense=round(total_expense, 2),
        total_monthly_net=round(total_income - total_expense, 2),
        total_budget_target=round(total_budget_target, 2),
        budget_target_set=any_target,
        scenario=scenario,
    )


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
