"""Monthly insights — A4.

A deterministic heuristic layer that surfaces notable month-over-month changes
(a category spiking vs. its recent average, cash-flow swings). This is always
available and cheap. An OPTIONAL LLM narrative can be generated on demand from
the same facts via :func:`generate_narrative` — never auto-invoked, so the
insights list stays fast and works with no provider configured.
"""
from __future__ import annotations

import sqlite3

from app.db import repository as repo
from app.services import llm
from app.services.llm_config import LLMConfig

# Only flag a change when it is both proportionally and absolutely meaningful.
PCT_THRESHOLD = 0.25
ABS_THRESHOLD = 20.0
TRAILING_MONTHS = 3


def _month_label(ym: str) -> str:
    year, month = ym.split("-")
    names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    return f"{names[int(month) - 1]} {year}"


def compute_insights(conn: sqlite3.Connection) -> list[dict]:
    """Return a list of ``{text, kind, category}`` insight rows (newest month)."""
    months = repo.observed_months(conn)
    if len(months) < 2:
        return []
    latest = months[-1]
    prior_months = months[-1 - TRAILING_MONTHS : -1]

    # Reshape monthly_series into {category_name: {ym: signed_total}}.
    by_cat: dict[str, dict[str, float]] = {}
    income_name = None
    for row in repo.monthly_series(conn):
        name = row["category_name"] or "Uncategorized"
        by_cat.setdefault(name, {})[row["ym"]] = row["total"] or 0.0

    insights: list[dict] = []
    for name, series in by_cat.items():
        latest_total = series.get(latest, 0.0)
        prior_vals = [series.get(m, 0.0) for m in prior_months]
        if not prior_vals:
            continue
        avg_prior = sum(prior_vals) / len(prior_vals)

        is_income = latest_total > 0 or avg_prior > 0
        if is_income:
            income_name = name
            latest_mag, prior_mag = latest_total, avg_prior
        else:
            latest_mag, prior_mag = abs(latest_total), abs(avg_prior)

        if prior_mag < ABS_THRESHOLD:
            continue
        delta = latest_mag - prior_mag
        if abs(delta) < ABS_THRESHOLD:
            continue
        pct = delta / prior_mag
        if abs(pct) < PCT_THRESHOLD:
            continue

        direction = "up" if delta > 0 else "down"
        pct_txt = f"{abs(round(pct * 100))}%"
        if is_income:
            kind = "up" if delta > 0 else "down"
            text = f"{name} {direction} {pct_txt} vs. your recent average"
        else:
            # Rising spend is the notable/negative case.
            kind = "warn" if delta > 0 else "good"
            text = f"{name} spending {direction} {pct_txt} vs. your recent average"
        insights.append({"text": text, "kind": kind, "category": name})

    # Rank by proportional magnitude; spending changes first.
    insights.sort(key=lambda i: i["kind"] != "warn")
    _ = income_name  # (kept for narrative context; not otherwise needed)
    return [{"month": _month_label(latest), **i} for i in insights[:6]]


async def generate_narrative(
    config: LLMConfig, insights: list[dict]
) -> str:
    """Turn the heuristic insights into a one-paragraph plain-English summary.

    Raises :class:`~app.services.llm.LLMError` if the provider is unavailable.
    """
    if not insights:
        return "Not enough history yet to summarize trends."
    facts = "; ".join(i["text"] for i in insights)
    system = (
        "You are a concise personal-finance assistant. Given a list of factual "
        "month-over-month changes, write ONE short, friendly paragraph (max 3 "
        "sentences) summarizing what stands out. Do not invent numbers beyond "
        'those given. Respond as JSON: {"summary": "..."}.'
    )
    data = await llm.generate_json(config, system, f"Changes this month: {facts}")
    summary = str(data.get("summary", "")).strip()
    if not summary:
        raise llm.LLMError("empty narrative")
    return summary
