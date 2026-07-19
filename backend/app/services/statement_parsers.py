"""OFX/QFX and QIF statement parsers.

Both feed the same ``ParseReport`` shape as the CSV parser, so everything
downstream (dedupe, categorization, budgets) is format-agnostic.

* **OFX/QFX** — the Open Financial Exchange format. 1.x is SGML-ish (leaf tags
  often unclosed), 2.x is XML; a tolerant regex scan over ``<STMTTRN>`` blocks
  handles both.
* **QIF** — Quicken Interchange Format: line-prefixed records terminated by
  ``^`` (D=date, T/U=amount, P=payee, M=memo).
"""
from __future__ import annotations

import re

from app.services.csv_parser import (
    ParsedRow,
    ParseReport,
    _normalize_amount,
    _parse_date,
    parse_csv,
)

_STMTTRN_RE = re.compile(
    r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|\Z)", re.DOTALL | re.IGNORECASE
)
_TAG_RES = {
    "date": re.compile(r"<DTPOSTED>\s*([0-9]{8})", re.IGNORECASE),
    "amount": re.compile(r"<TRNAMT>\s*([-+]?[0-9.,]+)", re.IGNORECASE),
    "name": re.compile(r"<NAME>\s*([^<\r\n]+)", re.IGNORECASE),
    "memo": re.compile(r"<MEMO>\s*([^<\r\n]+)", re.IGNORECASE),
}
_ACCTID_RE = re.compile(r"<ACCTID>\s*([^<\r\n]+)", re.IGNORECASE)


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def parse_ofx(content: bytes, default_account: str = "") -> ParseReport:
    """Parse OFX/QFX bytes into normalized rows."""
    report = ParseReport()
    text = _decode(content)

    account = (default_account or "").strip()
    if not account:
        m = _ACCTID_RE.search(text)
        account = f"Account …{m.group(1).strip()[-4:]}" if m else "Imported Account"

    blocks = _STMTTRN_RE.findall(text)
    if not blocks:
        report.errors.append("No <STMTTRN> transactions found in OFX file.")
        return report

    for i, block in enumerate(blocks, start=1):
        date_m = _TAG_RES["date"].search(block)
        amount_m = _TAG_RES["amount"].search(block)
        name_m = _TAG_RES["name"].search(block) or _TAG_RES["memo"].search(block)
        if not (date_m and amount_m and name_m):
            report.errors.append(
                f"OFX transaction {i}: missing date/amount/name; skipped."
            )
            continue
        raw_date = date_m.group(1)
        date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        amount = _normalize_amount(amount_m.group(1))
        if amount is None:
            report.errors.append(f"OFX transaction {i}: unparseable amount; skipped.")
            continue
        report.rows.append(
            ParsedRow(
                date=date,
                raw_description=name_m.group(1).strip(),
                amount=amount,
                account_name=account,
            )
        )
    return report


def parse_qif(content: bytes, default_account: str = "") -> ParseReport:
    """Parse QIF bytes into normalized rows."""
    report = ParseReport()
    text = _decode(content)
    account = (default_account or "").strip() or "Imported Account"

    record: dict[str, str] = {}
    line_no = 0
    for line in text.splitlines():
        line_no += 1
        line = line.strip()
        if not line or line.startswith("!"):
            continue
        code, value = line[0].upper(), line[1:].strip()
        if code == "^":
            _flush_qif_record(report, record, account, line_no)
            record = {}
        elif code in ("D", "T", "U", "P", "M"):
            # U (amount, newer) wins over T when both are present.
            if code == "U" or (code == "T" and "amount" not in record):
                if code in ("T", "U"):
                    record["amount"] = value
            if code == "D":
                record["date"] = value
            elif code == "P":
                record["payee"] = value
            elif code == "M":
                record.setdefault("memo", value)
    if record:
        _flush_qif_record(report, record, account, line_no)

    if not report.rows and not report.errors:
        report.errors.append("No transactions found in QIF file.")
    return report


def _flush_qif_record(
    report: ParseReport, record: dict[str, str], account: str, line_no: int
) -> None:
    if not record:
        return
    date = _parse_date(record.get("date", ""))
    amount = _normalize_amount(record.get("amount", ""))
    desc = record.get("payee") or record.get("memo") or ""
    if date is None or amount is None or not desc:
        report.errors.append(
            f"QIF record ending line {line_no}: missing date/amount/payee; skipped."
        )
        return
    report.rows.append(
        ParsedRow(
            date=date, raw_description=desc, amount=amount, account_name=account
        )
    )


def sniff_format(filename: str, content: bytes) -> str:
    """Return 'ofx', 'qif', or 'csv' from the extension (content fallback)."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("ofx", "qfx"):
        return "ofx"
    if ext == "qif":
        return "qif"
    if ext == "csv":
        return "csv"
    head = _decode(content[:2000]).upper()
    if "<OFX>" in head or "<STMTTRN>" in head:
        return "ofx"
    if head.startswith("!TYPE") or "\n!TYPE" in head:
        return "qif"
    return "csv"


def parse_statement(
    filename: str,
    content: bytes,
    default_account: str = "Imported Account",
    mapping: dict[str, str] | None = None,
) -> ParseReport:
    """Parse any supported statement file (CSV/OFX/QFX/QIF) uniformly."""
    fmt = sniff_format(filename, content)
    if fmt == "ofx":
        return parse_ofx(content, default_account)
    if fmt == "qif":
        return parse_qif(content, default_account)
    return parse_csv(content, default_account, mapping=mapping)
