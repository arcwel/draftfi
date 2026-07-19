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


def test_manual_income_spending_override_totals(conn):
    # No transactions at all — user typed their numbers instead.
    params = SimulationParameters(monthly_inflow=5000, monthly_outflow=3200)
    summary = budget.compute_budget(conn, params, [])
    assert summary.total_monthly_income == 5000.0
    assert summary.total_monthly_expense == 3200.0
    assert summary.total_monthly_net == 1800.0


# --------------------------------------------------------------------------- #
# D2 — specific-month view
# --------------------------------------------------------------------------- #
def test_specific_month_view_uses_that_months_actuals(conn):
    _seed(
        conn,
        [
            ("2026-01-05", "STORE", -100.0, "Groceries"),  # Jan: 100
            ("2026-02-05", "STORE", -300.0, "Groceries"),  # Feb: 300
        ],
    )
    avg = budget.compute_budget(conn, SimulationParameters(), [])
    jan = budget.compute_budget(conn, SimulationParameters(), [], month="2026-01")
    feb = budget.compute_budget(conn, SimulationParameters(), [], month="2026-02")

    groc = lambda s: next(c for c in s.categories if c.name == "Groceries")  # noqa: E731
    assert groc(avg).monthly_amount == 200.0  # (100+300)/2 months
    assert groc(jan).monthly_amount == 100.0
    assert groc(feb).monthly_amount == 300.0
    assert avg.month is None
    assert feb.month == "2026-02"
    assert avg.available_months == ["2026-01", "2026-02"]


# --------------------------------------------------------------------------- #
# D4 — budget rollover
# --------------------------------------------------------------------------- #
def test_budget_rollover_carries_unspent(conn):
    _seed(
        conn,
        [
            ("2026-01-10", "GROC", -60.0, "Groceries"),   # Jan: spent 60 of 100
            ("2026-02-10", "GROC", -130.0, "Groceries"),  # Feb: spent 130
        ],
    )
    gid = repo.get_category_by_name(conn, "Groceries")["id"]
    repo.set_category_budget(conn, gid, 100.0, rollover=True)

    feb = budget.compute_budget(conn, SimulationParameters(), [], month="2026-02")
    g = next(c for c in feb.categories if c.name == "Groceries")
    # Jan left 40 unspent → Feb effective budget = 100 + 40 = 140.
    assert g.carried_over == 40.0
    assert g.effective_budget == 140.0
    assert g.over_budget is False  # 130 < 140

    # Without rollover, 130 > 100 → over budget.
    repo.set_category_budget(conn, gid, 100.0, rollover=False)
    feb2 = budget.compute_budget(conn, SimulationParameters(), [], month="2026-02")
    g2 = next(c for c in feb2.categories if c.name == "Groceries")
    assert g2.over_budget is True
    assert g2.carried_over is None


# --------------------------------------------------------------------------- #
# D1/D3 — trends
# --------------------------------------------------------------------------- #
def test_trends_cashflow_and_series(conn):
    _seed(
        conn,
        [
            ("2026-01-01", "PAY", 4000.0, "Income"),
            ("2026-01-15", "RENT", -1500.0, "Housing"),
            ("2026-02-01", "PAY", 4200.0, "Income"),
            ("2026-02-15", "RENT", -1500.0, "Housing"),
            ("2026-02-20", "FOOD", -200.0, "Groceries"),
        ],
    )
    trends = budget.compute_trends(conn)
    assert trends.months == ["2026-01", "2026-02"]

    jan = next(p for p in trends.cashflow if p.month == "2026-01")
    feb = next(p for p in trends.cashflow if p.month == "2026-02")
    assert jan.income == 4000.0 and jan.expense == 1500.0 and jan.net == 2500.0
    assert feb.income == 4200.0 and feb.expense == 1700.0 and feb.net == 2500.0

    housing = next(c for c in trends.categories if c.name == "Housing")
    amounts = {p.month: p.amount for p in housing.series}
    assert amounts == {"2026-01": 1500.0, "2026-02": 1500.0}
    groceries = next(c for c in trends.categories if c.name == "Groceries")
    # Groceries only appear in Feb → Jan filled with 0.
    assert {p.month: p.amount for p in groceries.series} == {
        "2026-01": 0.0,
        "2026-02": 200.0,
    }
