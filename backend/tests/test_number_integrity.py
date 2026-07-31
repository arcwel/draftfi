"""The tests that would have caught the bugs a green suite still shipped.

A 215-test suite was passing while every amount in a real 10,371-row file was
sign-inverted, while the runway chart and the budget panel disagreed about the
same history by threefold, and while a pydantic Literal that the database could
violate 500'd the main endpoint. Three structural gaps let all of that through:

1. **No fixture used the failing convention.** Every sample file was already in
   DraftFi's sign convention, so nothing exercised the case that actually broke
   — a single Amount column where a charge is positive.
2. **Assertions stopped at boundaries.** Signs were checked at the parser, the
   simulation was checked on hand-built parameter objects. Nothing ran
   parse → import → categorize → aggregate → forecast and asserted the number a
   user would read off the screen. Every bug lived in those seams.
3. **Nothing cross-checked the aggregates against each other.** Three of the
   worst findings were all "two functions that should agree, don't."

So these tests are deliberately end-to-end and comparative rather than unit.
"""
from __future__ import annotations

import asyncio
import sqlite3
from typing import get_args

import pytest

from app.db import repository as repo
from app.db.schema import initialize
from app.models.schemas import Resolution, SimulationParameters
from app.services import budget, ingestion, signs, simulation
from app.services.csv_parser import number_duplicates, parse_csv


def _import(conn, name: str, content: bytes, account: str = "Test Account"):
    status = ingestion.JobStatus(job_id="test")
    return asyncio.run(
        ingestion.run_import(conn, [(name, content)], account, status)
    )


def _add(conn, date, desc, amount, category, i, account="Checking"):
    row = repo.get_category_by_name(conn, category)
    repo.insert_transaction(
        conn,
        {
            "date": date,
            "raw_description": desc,
            "amount": amount,
            "account_name": account,
            "category_id": int(row["id"]) if row else None,
            "clean_merchant": desc,
            "resolution": "manual",
            "import_hash": f"ni{i}",
            "canonical_key": desc,
        },
    )


# --------------------------------------------------------------------------- #
# 1. End to end, in the convention that actually broke
# --------------------------------------------------------------------------- #
CARD_CSV = b"""Date,Description,Amount
2025-03-01,NETFLIX.COM,15.99
2025-03-02,STARBUCKS STORE 44,5.75
2025-03-03,SHELL OIL 99,48.10
2025-03-04,CHEVRON 001,52.00
2025-03-05,TRADER JOES 099,88.20
2025-03-06,DOORDASH,31.15
2025-03-07,SPOTIFY USA,11.99
2025-03-08,CHIPOTLE 4412,14.85
2025-03-09,WHOLE FOODS,62.40
2025-03-10,NETFLIX.COM,15.99
"""


def test_a_card_export_with_positive_charges_is_stored_as_spending(conn):
    """The whole-file case, through the real import path.

    The parser-level tests all used fixtures that were already correctly signed,
    so nothing ever ran a positive-charge card export end to end. When the
    inversion fix was wired in it passed ``import_hash`` to
    ``dataclasses.replace`` — a @property, not a field — and every such import
    died with a TypeError and stored zero rows. Green suite, broken import.
    """
    status = _import(conn, "amex.csv", CARD_CSV, account="Amex")

    assert status.state == "done"
    assert status.imported == 10, f"nothing imported: {status.errors}"
    amounts = [r["amount"] for r in repo.list_transactions(conn)]
    assert all(a < 0 for a in amounts), amounts
    assert any("inverted" in e for e in status.errors)


def test_a_correctly_signed_file_survives_the_same_path(conn):
    """The other half of the guarantee: don't 'fix' what isn't broken."""
    good = CARD_CSV.replace(b",1", b",-1").replace(b",5", b",-5").replace(
        b",4", b",-4"
    ).replace(b",8", b",-8").replace(b",3", b",-3").replace(b",6", b",-6")
    status = _import(conn, "checking.csv", good, account="Checking")
    assert status.imported == 10
    assert all(r["amount"] < 0 for r in repo.list_transactions(conn))


def test_two_files_in_one_job_are_judged_separately(conn):
    """A correctly-signed checking export must not be flipped by a card export
    sitting next to it in the same drop."""
    checking = b"Date,Description,Amount\n" + b"".join(
        f"2025-04-{d:02d},ACME PAYROLL,5000.00\n".encode() for d in range(1, 10)
    ) + b"".join(
        f"2025-04-{d:02d},SAFEWAY 1234,-80.00\n".encode() for d in range(10, 19)
    )
    status = ingestion.JobStatus(job_id="test")
    asyncio.run(
        ingestion.run_import(
            conn,
            [("checking.csv", checking), ("amex.csv", CARD_CSV)],
            "Checking",
            status,
        )
    )
    rows = repo.list_transactions(conn)
    payroll = [r for r in rows if "PAYROLL" in r["raw_description"]]
    netflix = [r for r in rows if "NETFLIX" in r["raw_description"]]
    assert payroll and all(r["amount"] > 0 for r in payroll), "payroll was flipped"
    assert netflix and all(r["amount"] < 0 for r in netflix), "card was not flipped"


# --------------------------------------------------------------------------- #
# 2. The repair must not oscillate
# --------------------------------------------------------------------------- #
def test_repair_leaves_a_database_whose_signals_disagree_alone(conn):
    """The exact shape that inverted the whole file on every launch.

    Correct payroll plus unnormalised card charges makes the income anchors say
    "fine" and the expense anchors say "inverted". The old code checked income
    first, acted on whichever spoke up, and each flip made the other one fire —
    so every restart negated every amount in the database, forever.
    """
    for i in range(10):
        _add(conn, f"2025-05-{i + 1:02d}", f"ACME PAYROLL {i}", 5000.0, "Income", i)
    for i in range(10):
        _add(conn, f"2025-05-{i + 11:02d}", f"NETFLIX.COM {i}", 15.99, "Entertainment", 100 + i)
    conn.commit()

    before = sorted(r["amount"] for r in repo.list_transactions(conn))
    for _ in range(3):  # three "launches"
        signs.repair_existing(conn)
    after = sorted(r["amount"] for r in repo.list_transactions(conn))
    assert after == before


def test_repair_runs_at_most_once(conn):
    for i in range(10):
        _add(conn, f"2025-06-{i + 1:02d}", f"ACME PAYROLL {i}", -2500.0, "Income", i)
    conn.commit()
    assert signs.repair_existing(conn) == 10
    assert signs.repair_existing(conn) == 0
    assert all(r["amount"] > 0 for r in repo.list_transactions(conn))


def test_refunds_are_not_evidence_of_inversion():
    """A refund from an expense merchant is positive AND correct."""
    pairs = [(f"AMAZON.COM {i}", 60.0) for i in range(9)]
    pairs += [("NETFLIX.COM", -15.99), ("STARBUCKS 1", -5.0)]
    assert signs.detect_inverted(pairs)[0] is False


# --------------------------------------------------------------------------- #
# 3. Every screen must agree about the same history
# --------------------------------------------------------------------------- #
@pytest.fixture
def mixed_history(conn):
    """Twelve months containing income, spending, a transfer and an
    uncategorized row — one of each thing the aggregates used to treat
    differently from one another."""
    i = 0
    for m in range(1, 13):
        _add(conn, f"2025-{m:02d}-28", "ACME PAYROLL", 12824.0, "Income", i := i + 1)
        _add(conn, f"2025-{m:02d}-15", "SAFEWAY", -13318.0, "Groceries", i := i + 1)
        _add(conn, f"2025-{m:02d}-20", "TRANSFER TO SAVINGS", -400.0, "Transfers", i := i + 1)
        _add(conn, f"2025-{m:02d}-21", "MYSTERY VENDOR", -73.0, "Uncategorized", i := i + 1)
    conn.commit()
    return conn


def test_budget_trends_and_forecast_report_the_same_monthly_net(mixed_history):
    """The finding that made the runway chart lie.

    derive_baseline was the only aggregate that counted transfers, and
    category_breakdown was the only one that dropped uncategorized rows. The
    budget panel said -$494/mo while the chart drew -$167/mo, and nothing in
    the suite compared them.
    """
    conn = mixed_history
    inflow, outflow, _ = repo.run_rate(conn)
    rate_net = inflow - outflow

    summary = budget.compute_budget(conn, SimulationParameters(), [])
    baseline_in, baseline_out = simulation.derive_baseline(conn)
    trends = budget.compute_trends(conn)
    trend_net = sum(p.income - p.expense for p in trends.cashflow) / len(trends.cashflow)

    assert summary.total_monthly_net == pytest.approx(rate_net, abs=0.01)
    assert (baseline_in - baseline_out) == pytest.approx(rate_net, abs=0.01)
    assert trend_net == pytest.approx(rate_net, abs=0.01)


def test_transfers_are_excluded_and_uncategorized_money_is_not(mixed_history):
    conn = mixed_history
    _, outflow, _ = repo.run_rate(conn)
    # 13,318 groceries + 73 uncategorized, and NOT the 400 transfer.
    assert outflow == pytest.approx(13391.0, abs=0.01)


def test_money_moved_into_savings_is_not_income(conn):
    """A 401k contribution is money leaving. Counting it as income overstated
    the monthly net by the full investment amount — 167% in the reported case."""
    for m in range(1, 13):
        _add(conn, f"2025-{m:02d}-01", "ACME PAYROLL", 5000.0, "Income", m)
        _add(conn, f"2025-{m:02d}-05", "SAFEWAY", -600.0, "Groceries", 100 + m)
        _add(conn, f"2025-{m:02d}-10", "VANGUARD", -2000.0, "Savings & Investments", 200 + m)
    conn.commit()
    summary = budget.compute_budget(conn, SimulationParameters(), [])
    assert summary.total_monthly_income == pytest.approx(5000.0, abs=0.01)
    assert summary.total_monthly_expense == pytest.approx(2600.0, abs=0.01)
    assert summary.total_monthly_net == pytest.approx(2400.0, abs=0.01)


# --------------------------------------------------------------------------- #
# 4. The schema must not be able to disagree with the database
# --------------------------------------------------------------------------- #
def test_every_resolution_the_code_writes_is_in_the_response_model(conn):
    """The bug class that 500'd every /transactions call.

    ``Resolution`` is a Literal on the response model. Any value the write path
    can put in that column but the Literal omits makes the endpoint fail for
    every row, not just the odd one — and it fails at read time, long after the
    write that caused it.
    """
    allowed = set(get_args(Resolution))
    written = {
        "cache", "llm", "rule", "transfer", "override", "uncategorized",
        "manual", "split",
    }
    missing = written - allowed
    assert not missing, f"code writes resolutions the schema rejects: {missing}"


def test_no_stored_resolution_falls_outside_the_schema(mixed_history):
    """The same check against real data rather than a hand-kept list."""
    conn = mixed_history
    stored = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT resolution FROM transactions"
        ).fetchall()
        if r[0] is not None
    }
    assert stored <= set(get_args(Resolution)), stored - set(get_args(Resolution))


# --------------------------------------------------------------------------- #
# Parser-level data loss
# --------------------------------------------------------------------------- #
def test_a_zero_in_the_unused_debit_column_does_not_swallow_the_deposit():
    """Plenty of banks fill both columns and write 0.00 in the unused one."""
    report = parse_csv(
        b"Date,Description,Debit,Credit\n"
        b"2024-01-05,ACME PAYROLL,0.00,5000.00\n"
        b"2024-01-06,SAFEWAY,80.00,0.00\n",
        "Checking",
    )
    by_desc = {r.raw_description: r.amount for r in report.rows}
    assert by_desc["ACME PAYROLL"] == pytest.approx(5000.0)
    assert by_desc["SAFEWAY"] == pytest.approx(-80.0)


def test_identical_charges_on_one_day_are_not_deduped_away():
    """Two coffees are two transactions. They hash identically, and a UNIQUE
    index dropped the second while reporting it as a skipped duplicate."""
    rows = number_duplicates(
        parse_csv(
            b"Date,Description,Amount\n"
            b"2024-03-08,STARBUCKS STORE 44,-5.75\n"
            b"2024-03-08,STARBUCKS STORE 44,-5.75\n"
            b"2024-03-08,STARBUCKS STORE 44,-5.75\n",
            "Card",
        ).rows
    )
    assert len({r.import_hash for r in rows}) == 3


def test_reimporting_the_same_file_still_dedupes():
    """The ordinal is per file and deterministic, so the hashes are stable."""
    data = (
        b"Date,Description,Amount\n"
        b"2024-03-08,STARBUCKS STORE 44,-5.75\n"
        b"2024-03-08,STARBUCKS STORE 44,-5.75\n"
    )
    first = number_duplicates(parse_csv(data, "Card").rows)
    second = number_duplicates(parse_csv(data, "Card").rows)
    assert [r.import_hash for r in first] == [r.import_hash for r in second]


# --------------------------------------------------------------------------- #
# User decisions must survive maintenance operations
# --------------------------------------------------------------------------- #
def test_merging_a_category_keeps_the_merchant_memo_pointing_somewhere(conn):
    """A merge used to leave a user's decision with category_id NULL, which was
    invisible in the review queue and then crashed the next import."""
    dining = repo.get_category_by_name(conn, "Dining")
    groceries = repo.get_category_by_name(conn, "Groceries")
    repo.put_merchant_decision(
        conn,
        canonical_key="BLUE BOTTLE",
        display_name="Blue Bottle",
        category_id=int(dining["id"]),
        source="user",
    )
    conn.commit()

    repo.merge_category(conn, int(dining["id"]), int(groceries["id"]))
    conn.commit()

    memo = repo.get_merchant_decision(conn, "BLUE BOTTLE")
    assert memo["category_id"] == int(groceries["id"])
    assert memo["source"] == "user"


def test_a_freshly_imported_row_can_be_reviewed_without_a_restart(conn):
    """canonical_key was computed and then dropped on insert, so the review
    queue was empty until an app restart backfilled the column."""
    _import(
        conn,
        "card.csv",
        b"Date,Description,Amount\n"
        b"2025-07-01,SOME UNKNOWN VENDOR LLC 4471,-42.00\n"
        b"2025-07-02,SOME UNKNOWN VENDOR LLC 9912,-18.00\n",
        account="Card",
    )
    keys = [
        r["canonical_key"]
        for r in conn.execute("SELECT canonical_key FROM transactions").fetchall()
    ]
    assert all(keys), keys
    assert repo.review_queue_totals(conn)["merchants"] >= 1


# --------------------------------------------------------------------------- #
# Merchant matching must not collide
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "descriptor",
    ["ATTORNEY SMITH LAW", "MAXWELL PLUMBING", "RENTAL CAR CENTER"],
)
def test_short_rule_keys_do_not_swallow_unrelated_merchants(descriptor):
    """"ATT", "MAX" and "RENT" matched mid-word, so a solicitor's fee was filed
    under the phone bill — and both collapsed onto one canonical key, meaning an
    override on one silently recategorized the other."""
    from app.services import descriptors, merchant_rules

    assert merchant_rules.lookup(descriptors.canonical_key(descriptor)) is None


def test_real_merchants_still_resolve():
    """The boundary rule must not cost us the matches that were the point."""
    from app.services import descriptors, merchant_rules

    cases = {
        "ATT PAYMENT 800-288-2020": "Utilities",
        "AMAZON.COM AMZN.COM/BILL": "Shopping",
        "NETFLIX.COM": "Entertainment",
        "SHELL OIL 99 SAN DIEGO CA": "Transportation",
    }
    for raw, expected in cases.items():
        match = merchant_rules.lookup(descriptors.canonical_key(raw))
        assert match is not None and match.category == expected, raw


# --------------------------------------------------------------------------- #
# An unset starting position must not be reported as a finding
# --------------------------------------------------------------------------- #
def test_an_unset_cash_position_does_not_raise_a_false_alarm():
    series = simulation.run_simulation(
        SimulationParameters(monthly_inflow=12824, monthly_outflow=13318), [], []
    )
    assert series.cash_position_set is False
    assert series.failure_month is None
    assert not any(p.below_floor for p in series.runway)


def test_a_real_cash_position_is_still_checked_against_the_floor():
    series = simulation.run_simulation(
        SimulationParameters(
            starting_cash=1000, safety_floor=0,
            monthly_inflow=0, monthly_outflow=600, runway_months=12,
        ),
        [], [],
    )
    assert series.cash_position_set is True
    assert series.failure_month == 2


# --------------------------------------------------------------------------- #
# The macro chart must not contradict the runway chart
# --------------------------------------------------------------------------- #
def test_a_deficit_reduces_net_worth():
    """`max(inflow - outflow, 0)` floored losses, so the runway fell to zero
    while the macro chart beside it compounded upward at 6% a year."""
    series = simulation.run_simulation(
        SimulationParameters(
            starting_cash=0, starting_assets=50000, monthly_inflow=12824,
            monthly_outflow=13318, macro_years=5, annual_return_pct=6,
        ),
        [], [],
    )
    values = [p.net_worth for p in series.macro]
    assert values[-1] < values[0]


def test_a_financed_purchase_at_fair_value_does_not_create_net_worth():
    from app.models.schemas import Milestone

    params = SimulationParameters(
        starting_cash=80000, starting_assets=0, monthly_inflow=0,
        monthly_outflow=0, macro_years=5, annual_return_pct=0,
        annual_debt_rate_pct=0,
    )
    before = simulation.run_simulation(params, [], []).macro[0].net_worth
    house = Milestone(
        label="House", target_month=0, down_payment=80000, asset_value=400000,
        debt_incurred=320000, recurring_payment=0, recurring_months=0,
    )
    after = simulation.run_simulation(params, [house], [])
    assert after.macro[0].net_worth == pytest.approx(before, abs=0.01)
    # And the asset actually exists in the macro series at month 0.
    assert after.macro[0].total_assets == pytest.approx(400000.0, abs=0.01)


def test_starting_cash_counts_towards_net_worth():
    series = simulation.run_simulation(
        SimulationParameters(
            starting_cash=25000, starting_assets=50000, monthly_inflow=0,
            monthly_outflow=0, macro_years=5,
        ),
        [], [],
    )
    assert series.macro[0].net_worth == pytest.approx(75000.0, abs=0.01)


# --------------------------------------------------------------------------- #
# Split children are user decisions
# --------------------------------------------------------------------------- #
def test_the_deterministic_repair_does_not_rewrite_a_manual_split(conn):
    from app.services import recategorize

    housing = repo.get_category_by_name(conn, "Housing")
    shopping = repo.get_category_by_name(conn, "Shopping")
    _add(conn, "2025-08-01", "HOME DEPOT 4471", -500.0, "Shopping", 1)
    conn.commit()
    parent = repo.list_transactions(conn)[0]
    repo.split_transaction(
        conn,
        dict(parent),
        [
            {"amount": -400.0, "category_id": int(housing["id"]), "note": None},
            {"amount": -100.0, "category_id": int(shopping["id"]), "note": None},
        ],
    )
    conn.execute(
        "DELETE FROM app_settings WHERE key = ?", (recategorize.REPAIR_FLAG,)
    )
    conn.commit()

    recategorize.apply_deterministic_repair(conn)
    children = [
        r for r in repo.list_transactions(conn) if r["parent_tx_id"] is not None
    ]
    by_amount = {r["amount"]: r["category_name"] for r in children}
    assert by_amount[-400.0] == "Housing"
    assert by_amount[-100.0] == "Shopping"


# --------------------------------------------------------------------------- #
# Test isolation itself
# --------------------------------------------------------------------------- #
def test_the_suite_cannot_reach_the_users_real_files():
    """This suite once appended to the user's real log file. Assert the guards
    are actually in place rather than trusting that they still are."""
    import os

    from app.services import logging_setup

    assert os.environ.get("DRAFTFI_LOG_DIR")
    assert "draftfi-test-logs-" in str(logging_setup.log_dir())
    assert os.environ.get("DRAFTFI_DB_PATH") == ":memory:"


def test_an_empty_database_does_not_mark_the_repairs_as_done():
    """Both repairs used to flag themselves complete on a fresh install — i.e.
    for every user who opened the app before importing anything."""
    from app.services import recategorize

    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    initialize(fresh)
    flags = {
        r["key"]
        for r in fresh.execute(
            "SELECT key FROM app_settings WHERE key IN (?, ?)",
            (signs.SIGNS_REPAIR_FLAG, recategorize.REPAIR_FLAG),
        ).fetchall()
    }
    assert flags == set()
    fresh.close()
