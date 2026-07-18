"""API schema models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Resolution = Literal["cache", "llm", "override", "uncategorized"]


class Category(BaseModel):
    id: int
    name: str
    color: str
    monthly_budget: float | None = None


class Transaction(BaseModel):
    id: int
    date: str
    raw_description: str
    amount: float
    account_name: str
    category_id: int | None = None
    category_name: str | None = None
    category_color: str | None = None
    clean_merchant: str | None = None
    resolution: Resolution | None = None


class TransactionPage(BaseModel):
    items: list[Transaction]
    total: int
    limit: int
    offset: int


class ImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    skipped_invalid: int
    cache_hits: int
    llm_cleaned: int
    uncategorized: int
    errors: list[str] = Field(default_factory=list)


class CategoryOverride(BaseModel):
    category_id: int


class LLMStatus(BaseModel):
    available: bool
    latency_ms: float | None = None
    provider: str
    base_url: str
    model: str
    detail: str | None = None


class ProviderInfo(BaseModel):
    id: str
    label: str
    requires_key: bool
    is_local: bool
    default_model: str
    default_base_url: str
    model_hint: str
    has_key: bool


class LLMConfigOut(BaseModel):
    provider: str
    model: str
    base_url: str
    providers: list[ProviderInfo]


class LLMConfigIn(BaseModel):
    provider: str
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
class Milestone(BaseModel):
    label: str = "Milestone"
    target_month: int = Field(0, ge=0, description="Months from now (0 = today)")
    down_payment: float = 0.0
    recurring_payment: float = 0.0
    recurring_months: int = Field(0, ge=0)
    asset_value: float = 0.0
    debt_incurred: float = 0.0


class SimulationParameters(BaseModel):
    starting_cash: float = 0.0
    monthly_inflow: float | None = None
    monthly_outflow: float | None = None
    income_adjustment_pct: float = Field(0.0, ge=-30, le=30)
    safety_floor: float = 0.0
    runway_months: int = Field(36, ge=12, le=72)
    macro_years: int = Field(10, ge=5, le=30)
    annual_return_pct: float = 6.0
    annual_debt_rate_pct: float = 5.0
    starting_assets: float = 0.0
    starting_debt: float = 0.0


class SimulationRequest(BaseModel):
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    milestones: list[Milestone] = Field(default_factory=list)


class RunwayPoint(BaseModel):
    month: int
    cash: float
    below_floor: bool


class MacroPoint(BaseModel):
    year: float
    total_assets: float
    remaining_debt: float
    net_worth: float


class SimulationSeries(BaseModel):
    runway: list[RunwayPoint]
    macro: list[MacroPoint]
    failure_month: int | None = None
    safety_floor: float


class BranchBase(BaseModel):
    name: str
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    milestones: list[Milestone] = Field(default_factory=list)


class Branch(BranchBase):
    id: int
    is_base: bool


class BranchCreate(BaseModel):
    name: str
    source_branch_id: int | None = None


class BranchUpdate(BaseModel):
    name: str | None = None
    parameters: SimulationParameters | None = None
    milestones: list[Milestone] | None = None


class CompareResult(BaseModel):
    base: SimulationSeries
    branch: SimulationSeries
    base_branch_id: int
    branch_id: int


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #
class BudgetCategory(BaseModel):
    category_id: int | None
    name: str
    color: str
    is_income: bool
    monthly_amount: float          # avg monthly spend (expense) or income, +ve
    total: float                   # signed lifetime total
    transactions: int
    monthly_budget: float | None = None
    over_budget: bool = False
    budget_used_pct: float | None = None


class MilestoneImpact(BaseModel):
    label: str
    monthly_amount: float          # recurring monthly commitment
    start_month: int
    end_month: int
    one_time_cost: float           # down payment (0 if none)


class ScenarioBudgetImpact(BaseModel):
    income_adjustment_pct: float
    baseline_monthly_income: float
    scenario_monthly_income: float
    baseline_monthly_expense: float
    scenario_monthly_expense: float   # baseline + active recurring milestone cost
    recurring_milestone_cost: float
    one_time_cost: float
    baseline_monthly_net: float
    scenario_monthly_net: float
    net_delta: float
    milestones: list[MilestoneImpact]


class BudgetSummary(BaseModel):
    months_observed: int
    categories: list[BudgetCategory]
    total_monthly_income: float
    total_monthly_expense: float
    total_monthly_net: float
    total_budget_target: float          # sum of category targets that are set
    budget_target_set: bool
    scenario: ScenarioBudgetImpact


class BudgetRequest(BaseModel):
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    milestones: list[Milestone] = Field(default_factory=list)


class BudgetOverride(BaseModel):
    monthly_budget: float | None = None
