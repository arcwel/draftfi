"""Budget analytics: monthly averages, targets, and scenario impact."""
from __future__ import annotations

from app.db import repository as repo
from app.models.schemas import Milestone, SimulationParameters
from app.services import budget


def _seed(conn, rows):
    """rows: list of (date, raw, amount, category_name)."""
    for i, (date, raw, amount, cat_name) in enumerate(rows):
        cat_id = repo.upsert_category(conn, cat_name, "#123456")
        repo.insert_transaction(
            conn,
            {
                "date": date,
                "raw_description": raw,
                "amount": amount,
                "account_name": "Checking",
                "category_id": cat_id,
                "clean_merchant": raw,
                "resolution": "llm",
                "import_hash": f"h{i}",
            },
        )


def test_monthly_average_normalized_by_months(conn):
    # Two months of data: $600 groceries total -> $300/mo.
    _seed(
        conn,
        [
            ("2026-01-05", "STORE A", -200.0, "Groceries"),
            ("2026-01-20", "STORE B", -100.0, "Groceries"),
            ("2026-02-10", "STORE C", -300.0, "Groceries"),
        ],
    )
    summary = budget.compute_budget(conn, SimulationParameters(), [])
    assert summary.months_observed == 2
    groceries = next(c for c in summary.categories if c.name == "Groceries")
    assert groceries.monthly_amount == 300.0
    assert groceries.is_income is False
    assert summary.total_monthly_expense == 300.0


def test_income_split(conn):
    _seed(
        conn,
        [
            ("2026-01-01", "PAYROLL", 4000.0, "Income"),
            ("2026-01-15", "RENT", -1500.0, "Housing"),
        ],
    )
    summary = budget.compute_budget(conn, SimulationParameters(), [])
    assert summary.total_monthly_income == 4000.0
    assert summary.total_monthly_expense == 1500.0
    assert summary.total_monthly_net == 2500.0
    income = next(c for c in summary.categories if c.name == "Income")
    assert income.is_income is True


def test_budget_target_over_under(conn):
    _seed(conn, [("2026-01-05", "DINING OUT", -500.0, "Dining")])
    dining_id = repo.get_category_by_name(conn, "Dining")["id"]
    repo.set_category_budget(conn, dining_id, 300.0)
    summary = budget.compute_budget(conn, SimulationParameters(), [])
    dining = next(c for c in summary.categories if c.name == "Dining")
    assert dining.monthly_budget == 300.0
    assert dining.over_budget is True
    assert dining.budget_used_pct == round(500 / 300 * 100, 1)
    assert summary.budget_target_set is True
    assert summary.total_budget_target == 300.0


def test_scenario_income_adjustment(conn):
    _seed(
        conn,
        [
            ("2026-01-01", "PAYROLL", 5000.0, "Income"),
            ("2026-01-10", "SPEND", -3000.0, "Shopping"),
        ],
    )
    params = SimulationParameters(income_adjustment_pct=20)
    summary = budget.compute_budget(conn, params, [])
    s = summary.scenario
    assert s.baseline_monthly_income == 5000.0
    assert s.scenario_monthly_income == 6000.0  # +20%
    assert s.baseline_monthly_net == 2000.0
    assert s.scenario_monthly_net == 3000.0
    assert s.net_delta == 1000.0


def test_scenario_recurring_milestone_reduces_net(conn):
    _seed(
        conn,
        [
            ("2026-01-01", "PAYROLL", 5000.0, "Income"),
            ("2026-01-10", "SPEND", -3000.0, "Shopping"),
        ],
    )
    milestone = Milestone(
        label="Car Loan",
        target_month=3,
        down_payment=4000,
        recurring_payment=450,
        recurring_months=60,
    )
    summary = budget.compute_budget(conn, SimulationParameters(), [milestone])
    s = summary.scenario
    assert s.recurring_milestone_cost == 450.0
    assert s.one_time_cost == 4000.0
    assert s.scenario_monthly_expense == 3000.0 + 450.0
    assert s.scenario_monthly_net == 5000.0 - 3450.0
    assert s.net_delta == -450.0
    assert s.milestones[0].label == "Car Loan"
    assert s.milestones[0].end_month == 63


def test_empty_history_safe(conn):
    summary = budget.compute_budget(conn, SimulationParameters(), [])
    assert summary.months_observed == 1
    assert summary.categories == []
    assert summary.total_monthly_net == 0.0
