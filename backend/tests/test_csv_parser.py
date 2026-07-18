"""Phase 2.7 — CSV parsing across bank formats + malformed handling."""
from __future__ import annotations

from app.services.csv_parser import parse_csv


def test_chase_format(sample_csv):
    report = parse_csv(sample_csv("chase_checking.csv"))
    assert len(report.rows) == 6
    payroll = next(r for r in report.rows if "PAYROLL" in r.raw_description)
    assert payroll.amount == 3200.00
    assert payroll.date == "2026-01-05"
    assert payroll.account_name == "Chase Checking"


def test_amex_debit_credit_columns(sample_csv):
    report = parse_csv(sample_csv("amex_credit.csv"))
    # Debits become negative, credits positive.
    uber = next(r for r in report.rows if "UBER" in r.raw_description)
    payment = next(r for r in report.rows if "PAYMENT" in r.raw_description)
    assert uber.amount == -12.30
    assert payment.amount == 500.00


def test_euro_semicolon_and_parenthesized_negatives(sample_csv):
    report = parse_csv(sample_csv("euro_bank.csv"))
    assert len(report.rows) == 3
    tesco = next(r for r in report.rows if "TESCO" in r.raw_description)
    salary = next(r for r in report.rows if "SALARY" in r.raw_description)
    assert tesco.amount == -54.20  # (54.20) -> negative
    assert tesco.date == "2026-01-15"  # DD/MM/YYYY
    assert salary.amount == 2500.00


def test_malformed_reports_errors_not_crash(sample_csv):
    report = parse_csv(sample_csv("malformed.csv"))
    assert report.rows == []
    assert report.errors  # a descriptive error is reported


def test_import_hash_stable_and_distinct():
    from app.services.csv_parser import ParsedRow

    a = ParsedRow("2026-01-01", "COFFEE", -3.5, "Checking")
    b = ParsedRow("2026-01-01", "COFFEE", -3.5, "Checking")
    c = ParsedRow("2026-01-02", "COFFEE", -3.5, "Checking")
    assert a.import_hash == b.import_hash
    assert a.import_hash != c.import_hash
