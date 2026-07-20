"""API schema models."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Resolution = Literal["cache", "llm", "override", "uncategorized", "manual", "split"]


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
    parent_tx_id: int | None = None
    is_split_parent: bool = False
    note: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_from_db(cls, v):
        """The DB stores tags as a JSON string; accept both forms."""
        if v is None:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return v


class TransactionPage(BaseModel):
    items: list[Transaction]
    total: int
    limit: int
    offset: int


class CategoryOverride(BaseModel):
    category_id: int


class TransactionCreate(BaseModel):
    date: str
    amount: float
    raw_description: str = Field(min_length=1)
    account_name: str = "Manual Entry"
    category_id: int | None = None
    clean_merchant: str | None = None
    note: str | None = None
    tags: list[str] = Field(default_factory=list)


class TransactionUpdate(BaseModel):
    date: str | None = None
    amount: float | None = None
    raw_description: str | None = None
    account_name: str | None = None
    category_id: int | None = None
    clean_merchant: str | None = None
    note: str | None = None
    tags: list[str] | None = None


class SplitPart(BaseModel):
    amount: float
    category_id: int | None = None
    note: str | None = None


class SplitRequest(BaseModel):
    splits: list[SplitPart] = Field(min_length=2, max_length=10)


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str = Field(default="#64748B", pattern=r"^#[0-9a-fA-F]{6}$")


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CategoryMerge(BaseModel):
    target_id: int


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


# A1: on-demand connection test result.
class LLMTestResult(BaseModel):
    ok: bool
    latency_ms: float | None = None
    detail: str | None = None


# A2: live model list for the picker (with free-text fallback on the client).
class LLMModelsResult(BaseModel):
    models: list[str] = Field(default_factory=list)
    detail: str | None = None


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
    # E1: annual interest rate for the loan behind `debt_incurred`. When set,
    # the recurring payment is split into interest + principal (amortized).
    # None falls back to the scenario's annual_debt_rate_pct.
    apr: float | None = Field(default=None, ge=0, le=100)


class ChangeEvent(BaseModel):
    """E2: a step change to monthly income or expense from `month` onward."""

    label: str = "Change"
    month: int = Field(0, ge=0, description="Months from now the change takes effect")
    kind: Literal["income", "expense"]
    mode: Literal["set", "delta"] = "set"  # set = new absolute level; delta = +/-
    amount: float = 0.0


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
    # E3: used to derive real (inflation-adjusted) net worth alongside nominal.
    annual_inflation_pct: float = Field(0.0, ge=0, le=20)


class SimulationRequest(BaseModel):
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    milestones: list[Milestone] = Field(default_factory=list)
    events: list[ChangeEvent] = Field(default_factory=list)


class RunwayPoint(BaseModel):
    month: int
    cash: float
    below_floor: bool


class MacroPoint(BaseModel):
    year: float
    total_assets: float
    remaining_debt: float
    net_worth: float
    real_net_worth: float = 0.0  # E3: net worth in today's dollars


class SimulationSeries(BaseModel):
    runway: list[RunwayPoint]
    macro: list[MacroPoint]
    failure_month: int | None = None
    safety_floor: float


class BranchBase(BaseModel):
    name: str
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    milestones: list[Milestone] = Field(default_factory=list)
    events: list[ChangeEvent] = Field(default_factory=list)


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
    events: list[ChangeEvent] | None = None


class CompareResult(BaseModel):
    base: SimulationSeries
    branch: SimulationSeries
    base_branch_id: int
    branch_id: int


# --- E4: multi-branch compare -------------------------------------------- #
class CompareRequest(BaseModel):
    branch_ids: list[int] = Field(default_factory=list)


class ScenarioSeries(BaseModel):
    branch_id: int
    name: str
    is_base: bool
    series: SimulationSeries


class DeltaCell(BaseModel):
    branch_id: int
    name: str
    is_base: bool
    cash: float | None = None        # runway cash at the checkpoint month
    net_worth: float | None = None   # macro net worth at the checkpoint month
    cash_delta: float | None = None  # vs. base (None for the base row)
    net_delta: float | None = None


class DeltaRow(BaseModel):
    month: int
    cells: list[DeltaCell]


class MultiCompareResult(BaseModel):
    scenarios: list[ScenarioSeries]
    checkpoints: list[int]           # [12, 36, 72]
    deltas: list[DeltaRow]


# --- E5: goal tracking --------------------------------------------------- #
class GoalBase(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    kind: Literal["net_worth", "cash"]
    target_amount: float
    target_month: int = Field(ge=0, le=360)


class Goal(GoalBase):
    id: int


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal["net_worth", "cash"] | None = None
    target_amount: float | None = None
    target_month: int | None = Field(default=None, ge=0, le=360)


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
    rollover: bool = False
    # Populated only in the single-month view when rollover is on.
    carried_over: float | None = None
    effective_budget: float | None = None


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
    # None = all-time average view; else the specific YYYY-MM being shown.
    month: str | None = None
    available_months: list[str] = Field(default_factory=list)


class BudgetRequest(BaseModel):
    parameters: SimulationParameters = Field(default_factory=SimulationParameters)
    milestones: list[Milestone] = Field(default_factory=list)
    month: str | None = None  # YYYY-MM for a single month, else averaged


class BudgetOverride(BaseModel):
    monthly_budget: float | None = None
    rollover: bool | None = None


# --------------------------------------------------------------------------- #
# Trends (month-over-month)
# --------------------------------------------------------------------------- #
class CashflowPoint(BaseModel):
    month: str
    income: float
    expense: float
    net: float


class CategorySeriesPoint(BaseModel):
    month: str
    amount: float  # positive magnitude that month


class CategoryTrend(BaseModel):
    category_id: int | None
    name: str
    color: str
    is_income: bool
    series: list[CategorySeriesPoint]


class TrendsSummary(BaseModel):
    months: list[str]
    cashflow: list[CashflowPoint]
    categories: list[CategoryTrend]


# --------------------------------------------------------------------------- #
# Natural-language scenario parsing
# --------------------------------------------------------------------------- #
class ScenarioParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class ScenarioParseResult(BaseModel):
    milestones: list[Milestone] = Field(default_factory=list)
    # Partial SimulationParameters overrides (only keys the text implied).
    parameters: dict = Field(default_factory=dict)
    note: str | None = None


# --------------------------------------------------------------------------- #
# Subscriptions (A3) + insights (A4)
# --------------------------------------------------------------------------- #
class Subscription(BaseModel):
    merchant: str
    category: str
    color: str
    cadence: str                # weekly | biweekly | monthly | quarterly | annual
    amount: float               # typical charge
    monthly_cost: float         # normalized to a monthly figure
    occurrences: int
    last_charge: str
    active: bool                # recent enough to still be running


class SubscriptionsSummary(BaseModel):
    items: list[Subscription] = Field(default_factory=list)
    total_monthly: float = 0.0  # sum of active subscriptions only


class Insight(BaseModel):
    month: str
    text: str
    kind: str                   # warn (spend up) | good (spend down) | up | down
    category: str | None = None


class InsightsList(BaseModel):
    insights: list[Insight] = Field(default_factory=list)


class NarrativeResult(BaseModel):
    narrative: str


# --------------------------------------------------------------------------- #
# Desktop update check (F1)
# --------------------------------------------------------------------------- #
class UpdateInfo(BaseModel):
    current: str
    latest: str | None = None
    update_available: bool = False
    url: str


# --------------------------------------------------------------------------- #
# Security: app passcode (G2)
# --------------------------------------------------------------------------- #
class SecurityStatus(BaseModel):
    passcode_set: bool
    locked: bool


class PasscodeSet(BaseModel):
    passcode: str = Field(min_length=4, max_length=64)
    current: str | None = None  # required when changing an existing passcode


class PasscodeClear(BaseModel):
    current: str


class UnlockRequest(BaseModel):
    passcode: str


class UnlockResult(BaseModel):
    ok: bool


# --------------------------------------------------------------------------- #
# Preferences: currency + locale (G4)
# --------------------------------------------------------------------------- #
class Preferences(BaseModel):
    currency: str
    locale: str


class PreferencesUpdate(BaseModel):
    currency: str | None = Field(default=None, max_length=8)
    locale: str | None = Field(default=None, max_length=16)
