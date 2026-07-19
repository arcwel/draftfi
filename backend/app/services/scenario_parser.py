"""Natural-language scenario parsing (PRD §1: "natural language simulation
inputs").

Turns a sentence like "What if I buy a $400k house in 10 months with 20% down?"
into structured simulator inputs — milestones plus optional parameter
overrides — via the user's configured LLM. Output is validated through the
Pydantic schema, so a hallucinated shape can't corrupt a plan.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from app.models.schemas import (
    Milestone,
    ScenarioParseResult,
    SimulationParameters,
)
from app.services import llm, llm_config

# Parameter keys the model may override; anything else is dropped.
ALLOWED_PARAM_KEYS = set(SimulationParameters.model_fields.keys())

SYSTEM_PROMPT = """You convert a user's financial "what-if" description into \
JSON inputs for a personal-finance simulator. Today's date is __TODAY__. All \
months are integer indices counted from now (0 = this month, 12 = one year \
from now).

Respond with ONLY one JSON object, no markdown, in this exact shape:
{"milestones": [{"label": str, "target_month": int, "down_payment": number, \
"recurring_payment": number, "recurring_months": int, "asset_value": number, \
"debt_incurred": number}], "parameters": {}, "note": str}

Rules:
- A milestone is a large purchase/commitment. down_payment = one-time cash \
paid at target_month. asset_value = value added to net worth (e.g. home \
price). debt_incurred = financing taken on (price minus down payment). \
recurring_payment = the monthly payment; recurring_months = the term.
- If financing details are missing, estimate them from typical current rates \
(e.g. ~7% 30-year mortgage, ~7% 60-month auto loan) and say so in note.
- "parameters" may ONLY contain keys the user's text clearly implies, from: \
starting_cash, monthly_inflow, monthly_outflow, income_adjustment_pct (-30..30), \
safety_floor, annual_return_pct, annual_debt_rate_pct, starting_assets, \
starting_debt. Usually it is {}.
- note: one short sentence stating the assumptions you made.
- If the text is not a financial scenario, return {"milestones": [], \
"parameters": {}, "note": "Could not interpret this as a financial scenario."}"""


class ScenarioParseError(Exception):
    """Raised when the text can't be parsed into a scenario."""


async def parse_scenario(
    conn: sqlite3.Connection, text: str
) -> ScenarioParseResult:
    """Parse free text into milestones + parameter overrides via the LLM."""
    config = llm_config.resolve_config(conn)
    available, _, detail = await llm.health(config)
    if not available:
        raise ScenarioParseError(
            f"No LLM reachable ({detail or 'offline'}). Connect a provider in "
            "the sidebar to use natural-language scenarios."
        )

    system = SYSTEM_PROMPT.replace("__TODAY__", date.today().isoformat())
    try:
        data = await llm.generate_json(config, system, text)
    except llm.LLMError as exc:
        raise ScenarioParseError(str(exc)) from exc

    milestones: list[Milestone] = []
    for raw in data.get("milestones") or []:
        if not isinstance(raw, dict):
            continue
        try:
            milestones.append(Milestone(**{
                k: raw.get(k, Milestone.model_fields[k].default)
                for k in Milestone.model_fields
            }))
        except Exception:
            continue  # drop malformed milestones rather than failing the parse

    raw_params = data.get("parameters") or {}
    parameters = {
        k: v
        for k, v in raw_params.items()
        if k in ALLOWED_PARAM_KEYS and isinstance(v, int | float)
    }
    # Clamp the slider-backed field to its UI range.
    if "income_adjustment_pct" in parameters:
        parameters["income_adjustment_pct"] = max(
            -30.0, min(30.0, float(parameters["income_adjustment_pct"]))
        )

    note = data.get("note")
    return ScenarioParseResult(
        milestones=milestones,
        parameters=parameters,
        note=str(note) if note else None,
    )
