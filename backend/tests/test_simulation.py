"""Phase 5.10 — formula correctness, milestone timing, edge cases."""
from __future__ import annotations

import time

from app.models.schemas import ChangeEvent, Milestone, SimulationParameters
from app.services import simulation


def test_recurrence_formula():
    params = SimulationParameters(
        starting_cash=1000,
        monthly_inflow=500,
        monthly_outflow=300,
        runway_months=12,
    )
    series = simulation.run_simulation(params, [])
    # Month 0 = starting snapshot; each month adds net 200.
    assert series.runway[0].cash == 1000
    assert series.runway[1].cash == 1200
    assert series.runway[12].cash == 1000 + 200 * 12


def test_income_adjustment_scales_inflow():
    base = SimulationParameters(
        starting_cash=0, monthly_inflow=1000, monthly_outflow=0, runway_months=12
    )
    plus = base.model_copy(update={"income_adjustment_pct": 30})
    minus = base.model_copy(update={"income_adjustment_pct": -30})
    assert simulation.run_simulation(plus, []).runway[1].cash == 1300
    assert simulation.run_simulation(minus, []).runway[1].cash == 700


def test_milestone_down_payment_timing():
    params = SimulationParameters(
        starting_cash=5000,
        monthly_inflow=0,
        monthly_outflow=0,
        runway_months=12,
    )
    m = Milestone(label="House", target_month=3, down_payment=2000)
    series = simulation.run_simulation(params, [m])
    assert series.runway[2].cash == 5000
    assert series.runway[3].cash == 3000  # down payment hits at month 3
    assert series.runway[4].cash == 3000


def test_safety_floor_flags_failure_month():
    params = SimulationParameters(
        starting_cash=1000,
        monthly_inflow=0,
        monthly_outflow=300,
        safety_floor=500,
        runway_months=12,
    )
    series = simulation.run_simulation(params, [])
    # 1000 -> 700 (m1) -> 400 (m2) crosses floor of 500 at month 2.
    assert series.failure_month == 2
    assert series.runway[2].below_floor is True
    assert series.runway[1].below_floor is False


def test_macro_series_compounds_and_yearly_sampled():
    params = SimulationParameters(
        starting_cash=0,
        monthly_inflow=0,
        monthly_outflow=0,
        starting_assets=10000,
        annual_return_pct=6,
        macro_years=10,
    )
    series = simulation.run_simulation(params, [])
    assert len(series.macro) == 11  # years 0..10 inclusive
    assert series.macro[0].total_assets == 10000
    # Effective-annual 6% compounded monthly over 10y = (1.06)^10 ~ 1.7908x
    assert 17900 < series.macro[-1].total_assets < 17920


def test_zero_income_edge_case():
    params = SimulationParameters(
        starting_cash=100, monthly_inflow=0, monthly_outflow=0, runway_months=24
    )
    series = simulation.run_simulation(params, [])
    assert all(p.cash == 100 for p in series.runway)


def test_performance_under_budget():
    params = SimulationParameters(
        starting_cash=10000,
        monthly_inflow=5000,
        monthly_outflow=4000,
        runway_months=72,
        macro_years=30,
    )
    milestones = [Milestone(target_month=i, down_payment=100) for i in range(20)]
    start = time.perf_counter()
    simulation.run_simulation(params, milestones)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Engine alone must leave ample headroom under the 150ms end-to-end budget.
    assert elapsed_ms < 50


# --------------------------------------------------------------------------- #
# E1 — loan amortization
# --------------------------------------------------------------------------- #
def test_amortization_splits_interest_and_principal():
    # $12,000 loan at 12% APR (1%/mo), $1,000/mo for 12 months. First month's
    # interest is 120, so only 880 retires principal -> balance 11,120.
    params = SimulationParameters(
        starting_assets=0,
        starting_debt=0,
        monthly_inflow=0,
        monthly_outflow=0,
        macro_years=5,
    )
    # $398.57/mo fully amortizes $12,000 at 1%/mo over 36 payments. The loan
    # originates at month 1 and runs through month 37.
    m = Milestone(
        label="Auto loan",
        target_month=1,
        asset_value=12000,
        debt_incurred=12000,
        recurring_payment=398.57,
        recurring_months=36,
        apr=12,
    )
    series = simulation.run_simulation(params, [m])
    # Year 1 (month 12): only a year of payments made, so a large balance remains
    # (interest drag keeps it above a naive principal-minus-payments figure).
    debt_y1 = series.macro[1].remaining_debt
    assert 8000 < debt_y1 < 12000
    # By year 5 the loan is fully amortized (term ended at month 37).
    assert series.macro[-1].remaining_debt < 1


def test_amortization_vs_interest_free_debt():
    # A milestone with debt but no payment just accrues interest (grows).
    params = SimulationParameters(macro_years=5, monthly_inflow=0, monthly_outflow=0)
    m = Milestone(target_month=1, debt_incurred=10000, apr=10)
    series = simulation.run_simulation(params, [m])
    assert series.macro[-1].remaining_debt > 10000


# --------------------------------------------------------------------------- #
# E2 — income/expense change events
# --------------------------------------------------------------------------- #
def test_income_set_event_raises_inflow_from_month():
    params = SimulationParameters(
        starting_cash=0, monthly_inflow=1000, monthly_outflow=0, runway_months=12
    )
    ev = ChangeEvent(kind="income", mode="set", amount=3000, month=6)
    series = simulation.run_simulation(params, [], [ev])
    # Months 1-5 add 1000; month 6 onward adds 3000.
    assert series.runway[5].cash == 5000
    assert series.runway[6].cash == 8000
    assert series.runway[7].cash == 11000


def test_expense_delta_event_lowers_spend():
    params = SimulationParameters(
        starting_cash=10000, monthly_inflow=0, monthly_outflow=1000, runway_months=12
    )
    ev = ChangeEvent(kind="expense", mode="delta", amount=-400, month=3)
    series = simulation.run_simulation(params, [], [ev])
    # m1,m2: -1000 each -> 8000. m3 onward: -600 each.
    assert series.runway[2].cash == 8000
    assert series.runway[3].cash == 7400
    assert series.runway[4].cash == 6800


def test_income_event_still_scaled_by_adjustment_slider():
    params = SimulationParameters(
        starting_cash=0,
        monthly_inflow=1000,
        monthly_outflow=0,
        income_adjustment_pct=10,
        runway_months=12,
    )
    ev = ChangeEvent(kind="income", mode="set", amount=2000, month=1)
    series = simulation.run_simulation(params, [], [ev])
    assert series.runway[1].cash == 2200  # 2000 * 1.10


# --------------------------------------------------------------------------- #
# E3 — inflation adjustment
# --------------------------------------------------------------------------- #
def test_real_net_worth_deflated_by_inflation():
    params = SimulationParameters(
        starting_assets=10000,
        annual_return_pct=0,
        annual_inflation_pct=3,
        macro_years=10,
        monthly_inflow=0,
        monthly_outflow=0,
    )
    series = simulation.run_simulation(params, [])
    end = series.macro[-1]
    assert end.net_worth == 10000  # nominal unchanged at 0% return
    # Real value deflated ~ 10000 / 1.03^10 ≈ 7441.
    assert 7400 < end.real_net_worth < 7480


def test_real_equals_nominal_without_inflation():
    params = SimulationParameters(starting_assets=5000, annual_return_pct=0)
    series = simulation.run_simulation(params, [])
    assert series.macro[-1].real_net_worth == series.macro[-1].net_worth


# --------------------------------------------------------------------------- #
# E4 — checkpoint values for the delta table
# --------------------------------------------------------------------------- #
def test_checkpoint_values_reads_runway_and_macro():
    params = SimulationParameters(
        starting_cash=1000,
        monthly_inflow=100,
        monthly_outflow=0,
        runway_months=36,
        starting_assets=0,
        macro_years=10,
    )
    series = simulation.run_simulation(params, [])
    cash, net = simulation.checkpoint_values(series, 12)
    assert cash == 1000 + 100 * 12
    assert net is not None
    # Month 72 is beyond the 36-month runway -> cash is None, net still available.
    cash72, net72 = simulation.checkpoint_values(series, 72)
    assert cash72 is None
    assert net72 is not None


# --------------------------------------------------------------------------- #
# E5 — goal evaluation
# --------------------------------------------------------------------------- #
def test_goal_on_and_off_track():
    params = SimulationParameters(
        starting_cash=1000, monthly_inflow=100, monthly_outflow=0, runway_months=36
    )
    series = simulation.run_simulation(params, [])
    # Cash at month 12 = 2200. Target 2000 -> on track; 5000 -> off track.
    proj, on = simulation.evaluate_goal(series, "cash", 2000, 12)
    assert proj == 2200 and on is True
    proj2, on2 = simulation.evaluate_goal(series, "cash", 5000, 12)
    assert proj2 == 2200 and on2 is False
