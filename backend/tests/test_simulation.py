"""Phase 5.10 — formula correctness, milestone timing, edge cases."""
from __future__ import annotations

import time

from app.models.schemas import Milestone, SimulationParameters
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
