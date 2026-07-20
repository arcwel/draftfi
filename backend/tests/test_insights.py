"""A3/A4 — recurring-charge detection and month-over-month insights."""
from __future__ import annotations

import pytest

from app.db import repository as repo
from app.services import insights, llm, subscriptions
from app.services.llm_config import LLMConfig


def _seed(conn, rows):
    """rows: list of (date, merchant, amount, category_name)."""
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


# --------------------------------------------------------------------------- #
# A3 — subscriptions
# --------------------------------------------------------------------------- #
def test_detects_monthly_subscription(conn):
    _seed(
        conn,
        [
            ("2026-01-05", "NETFLIX", -15.99, "Entertainment"),
            ("2026-02-05", "NETFLIX", -15.99, "Entertainment"),
            ("2026-03-05", "NETFLIX", -15.99, "Entertainment"),
            ("2026-04-05", "NETFLIX", -15.99, "Entertainment"),
            ("2026-04-06", "CORNER STORE", -4.20, "Groceries"),  # one-off
        ],
    )
    result = subscriptions.detect_subscriptions(conn)
    netflix = next(s for s in result["items"] if s["merchant"] == "NETFLIX")
    assert netflix["cadence"] == "monthly"
    assert netflix["occurrences"] == 4
    assert abs(netflix["monthly_cost"] - 15.99) < 0.5
    assert netflix["active"] is True
    # The one-off purchase is not a subscription.
    assert all(s["merchant"] != "CORNER STORE" for s in result["items"])
    assert result["total_monthly"] >= 15.99


def test_annual_subscription_normalized_to_monthly(conn):
    _seed(
        conn,
        [
            ("2024-06-01", "DOMAIN RENEWAL", -120.0, "Software Subscriptions"),
            ("2025-06-01", "DOMAIN RENEWAL", -120.0, "Software Subscriptions"),
            ("2026-06-01", "DOMAIN RENEWAL", -120.0, "Software Subscriptions"),
        ],
    )
    result = subscriptions.detect_subscriptions(conn)
    dom = next(s for s in result["items"] if s["merchant"] == "DOMAIN RENEWAL")
    assert dom["cadence"] == "annual"
    assert abs(dom["monthly_cost"] - 10.0) < 0.5  # 120 / 12


def test_irregular_charges_are_not_subscriptions(conn):
    _seed(
        conn,
        [
            ("2026-01-03", "RANDOM SHOP", -12.0, "Shopping"),
            ("2026-01-19", "RANDOM SHOP", -85.0, "Shopping"),
            ("2026-03-27", "RANDOM SHOP", -6.0, "Shopping"),
        ],
    )
    result = subscriptions.detect_subscriptions(conn)
    assert result["items"] == []


# --------------------------------------------------------------------------- #
# A4 — insights
# --------------------------------------------------------------------------- #
def test_flags_category_spending_spike(conn):
    _seed(
        conn,
        [
            ("2026-01-10", "DINER", -100.0, "Dining"),
            ("2026-02-10", "DINER", -100.0, "Dining"),
            ("2026-03-10", "DINER", -100.0, "Dining"),
            ("2026-04-10", "DINER", -200.0, "Dining"),  # latest month doubles
        ],
    )
    out = insights.compute_insights(conn)
    dining = next(i for i in out if i["category"] == "Dining")
    assert dining["kind"] == "warn"  # rising spend
    assert "up" in dining["text"]
    assert dining["month"] == "Apr 2026"


def test_no_insights_with_single_month(conn):
    _seed(conn, [("2026-01-10", "DINER", -100.0, "Dining")])
    assert insights.compute_insights(conn) == []


@pytest.mark.asyncio
async def test_narrative_uses_llm_summary(monkeypatch):
    async def fake_generate_json(config, system, prompt):
        assert "Dining spending up" in prompt  # facts passed through
        return {"summary": "Your dining spend jumped this month."}

    monkeypatch.setattr(llm, "generate_json", fake_generate_json)
    cfg = LLMConfig(provider="ollama", model="m", base_url="http://x", api_key=None)
    facts = [{"text": "Dining spending up 100% vs. your recent average"}]
    out = await insights.generate_narrative(cfg, facts)
    assert out == "Your dining spend jumped this month."


@pytest.mark.asyncio
async def test_narrative_empty_facts_needs_no_llm():
    cfg = LLMConfig(provider="ollama", model="m", base_url="http://x", api_key=None)
    out = await insights.generate_narrative(cfg, [])
    assert "history" in out.lower()
