"""Amount-direction detection, and the repairs built on it.

A real 10,371-transaction file was imported with money-out-positive, so the app
reported $31,244/mo income against $1,055/mo spending and every forecast built
on it was meaningless. Detection has to be certain enough to act on and humble
enough to leave an unfamiliar file alone.
"""
from __future__ import annotations

import pytest

from app.db import repository as repo
from app.services import merchant_rules, recategorize, signs


def _pairs(*items):
    return list(items)


def test_negative_payroll_means_the_file_is_inverted():
    pairs = _pairs(*[(f"SONY ELECTRONICS PAYROLL {i}", -3000.0) for i in range(10)])
    inverted, why = signs.detect_inverted(pairs)
    assert inverted is True
    assert "payroll" in why


def test_positive_expenses_also_prove_it():
    """A card-only export has no payroll in it, so known expense merchants are
    the other signal."""
    pairs = _pairs(
        ("NETFLIX.COM", 19.99), ("STARBUCKS 123", 5.75), ("SHELL OIL 99", 48.10),
        ("CHEVRON 001", 52.00), ("TRADER JOES 099", 88.20), ("DOORDASH", 31.15),
        ("SPOTIFY USA", 11.99), ("CHIPOTLE 4412", 14.85), ("WHOLE FOODS", 62.40),
    )
    inverted, why = signs.detect_inverted(pairs)
    assert inverted is True
    assert "expense" in why


def test_a_correctly_signed_file_is_left_alone():
    pairs = _pairs(
        ("SONY ELECTRONICS PAYROLL", 3000.0), ("NETFLIX.COM", -19.99),
        ("STARBUCKS 123", -5.75), ("SHELL OIL 99", -48.10),
        ("CHEVRON 001", -52.00), ("TRADER JOES 099", -88.20),
        ("DOORDASH", -31.15), ("SPOTIFY USA", -11.99), ("CHIPOTLE", -14.85),
    )
    assert signs.detect_inverted(pairs)[0] is False


def test_too_little_evidence_means_no_guess():
    """Guessing at the direction of someone's money is worse than doing nothing."""
    inverted, why = signs.detect_inverted(
        _pairs(("MYSTERY VENDOR", 42.0), ("ANOTHER ONE", 19.0))
    )
    assert inverted is False
    assert "not enough evidence" in why


def test_a_mixed_signal_does_not_trip_the_threshold():
    """Half wrong is not lopsided; the bar is deliberately high."""
    pairs = _pairs(*[(f"ACME PAYROLL {i}", 3000.0 if i % 2 else -3000.0)
                     for i in range(12)])
    assert signs.detect_inverted(pairs)[0] is False


def _arm_repair(conn):
    """Clear the one-shot flag.

    initialize() runs the repair during fixture setup, on an empty database, and
    marks it done — correct in production (a fresh install has nothing to
    repair), but it means a test has to re-arm it before adding rows.
    """
    conn.execute(
        "DELETE FROM app_settings WHERE key = ?", (recategorize.REPAIR_FLAG,)
    )
    conn.commit()


def _add(conn, raw, amount, i, category="Shopping", resolution="llm"):
    cat = repo.get_category_by_name(conn, category)
    repo.insert_transaction(
        conn,
        {
            "date": f"2026-02-{(i % 28) + 1:02d}",
            "raw_description": raw,
            "amount": amount,
            "account_name": "Card",
            "category_id": int(cat["id"]) if cat else None,
            "clean_merchant": raw,
            "resolution": resolution,
            "import_hash": f"sg{i}",
        },
    )


def test_repair_flips_a_whole_inverted_database(conn):
    for i in range(10):
        _add(conn, f"SONY ELECTRONICS PAYROLL {i}", -3000.0, i, category="Income")
    _add(conn, "NETFLIX.COM", 19.99, 50)
    conn.commit()

    flipped = signs.repair_existing(conn)
    assert flipped == 11
    rows = {r["raw_description"]: r["amount"] for r in repo.list_transactions(conn)}
    assert rows["NETFLIX.COM"] == pytest.approx(-19.99)
    assert rows["SONY ELECTRONICS PAYROLL 0"] == pytest.approx(3000.0)


def test_repair_is_idempotent(conn):
    """It runs on every launch, so a second pass must be a no-op — flipping
    twice would put the file back the way it was broken."""
    for i in range(10):
        _add(conn, f"ACME PAYROLL {i}", -2500.0, i, category="Income")
    conn.commit()

    assert signs.repair_existing(conn) == 10
    assert signs.repair_existing(conn) == 0
    assert repo.list_transactions(conn)[0]["amount"] > 0


def test_repair_leaves_a_correct_database_untouched(conn):
    for i in range(10):
        _add(conn, f"ACME PAYROLL {i}", 2500.0, i, category="Income")
    conn.commit()
    assert signs.repair_existing(conn) == 0


# --------------------------------------------------------------------------- #
# Deterministic repair
# --------------------------------------------------------------------------- #
def test_repair_moves_internal_transfers_out_of_income_and_savings(conn):
    _add(conn, "ONLINE TRANSFER FROM ANTHONY C GUIDRY REF #IB1", 500.0, 1,
         category="Income")
    _add(conn, "RECURRING TRANSFER TO GUIDRY A WAY2SAVE SAVINGS", -200.0, 2,
         category="Savings & Investments")
    _add(conn, "DISCOVER E-PAYMENT 220114 1893 GUIDRY ANTHONY", -300.0, 3,
         category="Fees & Interest")
    conn.commit()
    _arm_repair(conn)

    stats = recategorize.apply_deterministic_repair(conn)
    assert stats["transfers"] == 3
    names = {r["category_name"] for r in repo.list_transactions(conn)}
    assert names == {merchant_rules.CATEGORY_TRANSFERS}


def test_repair_never_touches_a_user_override(conn):
    _add(conn, "VENMO PAYMENT 123", -50.0, 1, category="Dining",
         resolution="override")
    conn.commit()
    _arm_repair(conn)
    recategorize.apply_deterministic_repair(conn)
    assert repo.list_transactions(conn)[0]["category_name"] == "Dining"


def test_repair_leaves_ambiguous_merchants_alone(conn):
    """Costco is groceries AND household AND petrol. Rewriting 337 rows to
    "Shopping" would impose an opinion, not fix an error."""
    _add(conn, "COSTCO WHSE #0455 SAN DIEGO CA", -240.0, 1, category="Groceries")
    _add(conn, "7-ELEVEN 34121 CA", -12.0, 2, category="Groceries")
    conn.commit()
    _arm_repair(conn)

    stats = recategorize.apply_deterministic_repair(conn)
    assert stats["skipped_ambiguous"] == 2
    assert {r["category_name"] for r in repo.list_transactions(conn)} == {"Groceries"}


def test_repair_does_categorize_an_ambiguous_merchant_that_had_nothing(conn):
    """Skipping is about not overwriting a judgement — an Uncategorized row has
    no judgement to protect."""
    _add(conn, "COSTCO WHSE #0455", -240.0, 1, category="Uncategorized")
    conn.commit()
    _arm_repair(conn)
    recategorize.apply_deterministic_repair(conn)
    assert repo.list_transactions(conn)[0]["category_name"] == "Shopping"


def test_repair_runs_only_once(conn):
    _add(conn, "VENMO PAYMENT 123", -50.0, 1, category="Dining")
    conn.commit()
    _arm_repair(conn)
    first = recategorize.apply_deterministic_repair(conn)
    assert first["transfers"] == 1
    assert recategorize.apply_deterministic_repair(conn) == {}
