"""Bank-statement CSV parsing and normalization.

Handles the messy reality of consumer bank exports: varying column names,
separate debit/credit columns, currency symbols, thousands separators,
parenthesized negatives, and assorted date formats. Malformed rows are
reported rather than aborting the whole import.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime

# Candidate header names (lower-cased) mapped to canonical fields.
DATE_KEYS = {"date", "transaction date", "posted date", "posting date", "trans date"}
DESC_KEYS = {
    "description",
    "raw description",
    "details",
    "memo",
    "name",
    "payee",
    "transaction",
    "narrative",
}
AMOUNT_KEYS = {"amount", "transaction amount", "value"}
DEBIT_KEYS = {"debit", "withdrawal", "withdrawals", "money out", "paid out"}
CREDIT_KEYS = {"credit", "deposit", "deposits", "money in", "paid in"}
ACCOUNT_KEYS = {"account", "account name", "account number", "card"}

DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%m/%d/%y",
    "%d/%m/%y",
    "%b %d, %Y",
    "%d %b %Y",
]


@dataclass
class ParsedRow:
    date: str
    raw_description: str
    amount: float
    account_name: str

    @property
    def import_hash(self) -> str:
        key = (
            f"{self.date}|{self.raw_description}|"
            f"{self.amount:.2f}|{self.account_name}"
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass
class ParseReport:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _normalize_amount(value: str) -> float | None:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    negative = v.startswith("(") and v.endswith(")")
    v = v.strip("()")
    # Drop currency symbols and thousands separators.
    v = v.replace("$", "").replace("£", "").replace("€", "").replace(",", "").strip()
    if v in ("", "-", "--"):
        return None
    try:
        amount = float(v)
    except ValueError:
        return None
    return -amount if negative else amount


def _parse_date(value: str) -> str | None:
    v = (value or "").strip()
    if not v:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _match(header: list[str], keys: set[str]) -> str | None:
    """Return the first header whose lower-cased name is in ``keys``."""
    for h in header:
        if h and h.strip().lower() in keys:
            return h
    return None


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_csv(content: bytes, default_account: str = "Imported Account") -> ParseReport:
    """Parse raw CSV bytes into normalized rows with per-row error reporting."""
    report = ParseReport()
    text = _decode(content)

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None:
        report.errors.append("Empty file or missing header row.")
        return report

    header = [h for h in reader.fieldnames if h is not None]
    date_col = _match(header, DATE_KEYS)
    desc_col = _match(header, DESC_KEYS)
    amount_col = _match(header, AMOUNT_KEYS)
    debit_col = _match(header, DEBIT_KEYS)
    credit_col = _match(header, CREDIT_KEYS)
    account_col = _match(header, ACCOUNT_KEYS)

    if desc_col is None:
        report.errors.append(
            f"Could not find a description column. Headers seen: {header}"
        )
        return report
    if amount_col is None and debit_col is None and credit_col is None:
        report.errors.append("Could not find an amount (or debit/credit) column.")
        return report

    for line_no, row in enumerate(reader, start=2):
        raw_desc = (row.get(desc_col) or "").strip()
        if not raw_desc:
            report.errors.append(f"Row {line_no}: empty description; skipped.")
            continue

        # Amount: single column, or a debit/credit pair.
        amount: float | None = None
        if amount_col is not None:
            amount = _normalize_amount(row.get(amount_col, ""))
        if amount is None and (debit_col or credit_col):
            debit = _normalize_amount(row.get(debit_col, "")) if debit_col else None
            credit = _normalize_amount(row.get(credit_col, "")) if credit_col else None
            if debit is not None:
                amount = -abs(debit)
            elif credit is not None:
                amount = abs(credit)
        if amount is None:
            report.errors.append(f"Row {line_no}: unparseable amount; skipped.")
            continue

        date = _parse_date(row.get(date_col, "")) if date_col else None
        if date is None:
            report.errors.append(
                f"Row {line_no}: unparseable/missing date; skipped."
            )
            continue

        account = (row.get(account_col) or "").strip() if account_col else ""
        report.rows.append(
            ParsedRow(
                date=date,
                raw_description=raw_desc,
                amount=amount,
                account_name=account or default_account,
            )
        )

    return report
