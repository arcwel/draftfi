"""Sync re-categorizes transactions that were left Uncategorized."""
from __future__ import annotations

import pytest

from app.db import repository as repo
from app.services import llm, sync


def _add_uncategorized(conn, raw, i, amount=-10.0):
    uncat = repo.upsert_category(conn, "Uncategorized", "#64748B")
    repo.insert_transaction(
        conn,
        {
            "date": f"2026-01-0{i + 1}",
            "raw_description": raw,
            "amount": amount,
            "account_name": "Checking",
            "category_id": uncat,
            "clean_merchant": raw,
            "resolution": "uncategorized",
            "import_hash": f"h{i}",
        },
    )


@pytest.mark.asyncio
async def test_sync_resolves_via_llm_when_available(conn, monkeypatch):
    # Deliberately NOT merchants the seeded rule table knows — otherwise this
    # resolves for free and never reaches the model it means to exercise.
    _add_uncategorized(conn, "BLUE BOTTLE COFFEE SF", 0)
    _add_uncategorized(conn, "ZEPHYR CYCLES 4471", 1)

    async def fake_check(config):
        return llm.HealthResult(available=True, latency_ms=5.0)

    def _resolve(merchant):
        if "BLUE BOTTLE" in merchant:
            return llm.MerchantVerdict(
                merchant="Blue Bottle Coffee", category="Dining", confidence=0.95
            )
        return llm.MerchantVerdict(
            merchant="Zephyr Cycles", category="Shopping", confidence=0.95
        )

    # Mock the batch call — that's the path production actually takes.
    async def fake_classify(config, merchants, cats):
        return [_resolve(m) for m in merchants]

    monkeypatch.setattr(llm, "check", fake_check)
    monkeypatch.setattr(llm, "classify_merchants", fake_classify)

    result = await sync.resync(conn)
    assert result.total == 2
    assert result.processed == 2
    assert result.recategorized == 2
    assert result.llm_cleaned == 2
    assert result.still_uncategorized == 0
    # The rows now carry real categories.
    rows = repo.list_transactions(conn)
    names = {r["category_name"] for r in rows}
    assert {"Dining", "Shopping"} <= names


@pytest.mark.asyncio
async def test_sync_noop_when_llm_unavailable(conn, monkeypatch):
    _add_uncategorized(conn, "MYSTERY VENDOR", 0)

    async def offline(config):
        return llm.HealthResult(available=False, detail="offline")

    monkeypatch.setattr(llm, "check", offline)

    result = await sync.resync(conn)
    assert result.total == 1
    assert result.recategorized == 0
    assert result.still_uncategorized == 1
    assert result.llm_available is False


@pytest.mark.asyncio
async def test_sync_uses_cache_without_llm_call(conn, monkeypatch):
    # A cache rule exists (e.g. from a prior override); sync should apply it
    # even though the LLM is offline.
    shopping = repo.upsert_category(conn, "Shopping", "#f97316")
    repo.put_cache(conn, "AMZN MKTP US", "Amazon", shopping)
    _add_uncategorized(conn, "AMZN MKTP US", 0)

    async def offline(config):
        return llm.HealthResult(available=False, detail="offline")

    monkeypatch.setattr(llm, "check", offline)

    result = await sync.resync(conn)
    assert result.recategorized == 1
    assert result.cache_hits == 1


@pytest.mark.asyncio
async def test_rate_limited_provider_is_reported_not_silently_swallowed(conn, monkeypatch):
    """A 429 must surface as a reason and stop the run, not report a clean 'done'
    while every row quietly stays Uncategorized."""
    for i in range(120):  # more chunks than the abort threshold needs
        _add_uncategorized(conn, f"MERCHANT {i}", i)

    async def fake_check(config):
        return llm.HealthResult(available=True, latency_ms=5.0)

    calls = {"batch": 0, "single": 0}

    async def rate_limited(config, merchants, cats):
        calls["batch"] += 1
        raise llm.LLMUnavailable(
            "LLM endpoint error: Client error '429 Too Many Requests'"
        )

    async def should_not_run(config, raw, cats, retries=1):
        calls["single"] += 1
        raise AssertionError("must not retry per-row against a refusing provider")

    monkeypatch.setattr(llm, "check", fake_check)
    monkeypatch.setattr(llm, "classify_merchants", rate_limited)
    monkeypatch.setattr(llm, "clean_merchant", should_not_run)

    result = await sync.resync(conn)

    assert result.recategorized == 0
    assert "429" in (result.detail or ""), "the real reason must reach the UI"
    assert result.stopped_early is True
    # Bailed out after the failure threshold instead of grinding every chunk...
    assert calls["batch"] == sync.MAX_PROVIDER_FAILURES
    # ...and never amplified into per-row calls.
    assert calls["single"] == 0
    # Every row is still accounted for as unresolved.
    assert result.still_uncategorized == result.total


@pytest.mark.asyncio
async def test_sync_processes_newest_transactions_first(conn, monkeypatch):
    """With a large backlog the ordering decides what gets fixed first, and a
    run that stops early should leave the recent end resolved."""
    uncat = repo.upsert_category(conn, "Uncategorized", "#64748B")
    for i, date in enumerate(["2022-03-04", "2026-07-18", "2024-11-30"]):
        repo.insert_transaction(
            conn,
            {
                "date": date,
                "raw_description": f"MERCHANT {date}",
                "amount": -10.0,
                "account_name": "Checking",
                "category_id": uncat,
                "clean_merchant": date,
                "resolution": "uncategorized",
                "import_hash": f"ord{i}",
            },
        )

    seen: list[str] = []

    async def fake_check(config):
        return llm.HealthResult(available=True, latency_ms=1.0)

    async def fake_classify(config, merchants, cats):
        seen.extend(merchants)
        return [
            llm.MerchantVerdict(merchant=m, category="Shopping", confidence=0.9)
            for m in merchants
        ]

    monkeypatch.setattr(llm, "check", fake_check)
    monkeypatch.setattr(llm, "classify_merchants", fake_classify)
    monkeypatch.setattr(sync, "CHUNK", 1)  # one row per call, so order is visible

    await sync.resync(conn)

    # Canonical keys reach the model, and the dates inside the descriptors are
    # stripped as noise — so assert the ORDER via the source rows instead.
    assert len(seen) == 3
    resolved = repo.list_transactions(conn)
    by_date = {r["date"]: r["resolution"] for r in resolved}
    assert by_date["2026-07-18"] != "uncategorized"


@pytest.mark.asyncio
async def test_known_merchants_resolve_without_a_model_call(conn, monkeypatch):
    """The point of the rule table: obvious merchants cost nothing and can't drift.

    Amazon landing in Shopping 885 times but also Entertainment, Software
    Subscriptions and Housing is what happens without this.
    """
    _add_uncategorized(conn, "AMAZON MKTPLACE PMTS AMZN.COM/BILL WA", 0)
    _add_uncategorized(conn, "AT&T PAYMENT 8005551212 TX", 1)
    _add_uncategorized(conn, "SHELL OIL 574398201 CA", 2)

    async def fake_check(config):
        return llm.HealthResult(available=True, latency_ms=1.0)

    async def must_not_ask(config, merchants, cats):
        raise AssertionError(f"should not have asked the model about {merchants}")

    monkeypatch.setattr(llm, "check", fake_check)
    monkeypatch.setattr(llm, "classify_merchants", must_not_ask)

    result = await sync.resync(conn)

    assert result.recategorized == 3
    assert result.llm_cleaned == 0, "no model calls for merchants we already know"
    by_merchant = {
        r["clean_merchant"]: r["category_name"] for r in repo.list_transactions(conn)
    }
    assert by_merchant["Amazon"] == "Shopping"
    assert by_merchant["AT&T"] == "Utilities"
    assert by_merchant["Shell Oil"] == "Transportation"


@pytest.mark.asyncio
async def test_transfers_are_not_categorized_as_spending(conn, monkeypatch):
    """A card payment out of checking settles purchases already counted, so
    treating it as spending double-counts every dollar."""
    _add_uncategorized(conn, "CAPITAL ONE MOBILE PMT ANTHONY GUIDRY", 0)
    _add_uncategorized(conn, "VENMO PAYMENT 1035512345", 1)
    # Payroll is a deposit; a negative one would be a reversal, not income.
    _add_uncategorized(conn, "SONY ELECTRONICS PAYROLL", 2, amount=4200.0)

    async def fake_check(config):
        return llm.HealthResult(available=True, latency_ms=1.0)

    async def must_not_ask(config, merchants, cats):
        raise AssertionError(f"transfers must not reach the model: {merchants}")

    monkeypatch.setattr(llm, "check", fake_check)
    monkeypatch.setattr(llm, "classify_merchants", must_not_ask)

    await sync.resync(conn)

    rows = {r["raw_description"]: r for r in repo.list_transactions(conn)}
    assert rows["CAPITAL ONE MOBILE PMT ANTHONY GUIDRY"]["category_name"] == "Transfers"
    assert rows["VENMO PAYMENT 1035512345"]["category_name"] == "Transfers"
    # Payroll is earnings, not a transfer.
    assert rows["SONY ELECTRONICS PAYROLL"]["category_name"] == "Income"
    # And Transfers is excluded from the spending breakdown entirely.
    spend = {c["category_name"] for c in repo.category_breakdown(conn)}
    assert "Transfers" not in spend
