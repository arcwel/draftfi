"""Detect and correct an inverted amount convention.

DraftFi's convention is **money in is positive, money out is negative** — every
aggregate in the app depends on it (spending is ``amount < 0``, income is
``amount > 0``).

Many real exports use the opposite. Credit-card statements in particular list a
charge as a positive number, because from the issuer's perspective a purchase
increases what you owe. Taken verbatim, that makes the app read your spending as
income: on a real 10,371-transaction file every one of 388 payroll and
interest-paid rows was negative while Netflix and Starbucks were positive, so the
app reported $31,244/mo income against $1,055/mo spending. The forecast built on
those numbers was meaningless.

Detection is anchored on transactions whose direction is not a matter of opinion:

* **Income anchors** — payroll, direct deposits, interest paid. Money in. If
  these are negative, the file is inverted.
* **Expense anchors** — descriptors that hit a known expense merchant rule
  (Netflix, Starbucks, a petrol station). Money out. If these are positive, the
  file is inverted.

Two independent signals, either of which is sufficient, because a card-only
export has no payroll in it and a checking-only export may have few recognisable
merchants. Both require a minimum sample, and when neither has enough evidence
the amounts are left exactly as they came in — guessing at the direction of
someone's money is worse than leaving it alone.
"""
from __future__ import annotations

import logging
import re

from app.services import descriptors, merchant_rules

log = logging.getLogger("draftfi.signs")

# Money-in by definition. Narrower than merchant_rules' income patterns: this
# list must contain nothing whose direction is arguable.
_INCOME_ANCHORS = re.compile(
    r"\b(PAYROLL|DIRECT DEP|DIR DEP|SALARY|PAYCHECK|INTEREST PAID|"
    r"DIVIDEND|TAX REF|IRS TREAS|SSA TREAS)\b",
    re.IGNORECASE,
)

# Categories that only ever represent money leaving. Income and Transfers are
# excluded: transfers go both ways, so they say nothing about direction.
_EXPENSE_CATEGORIES = frozenset(
    {
        "Groceries", "Dining", "Shopping", "Healthcare", "Entertainment",
        "Software Subscriptions", "Transportation", "Housing", "Utilities",
        "Travel", "Fees & Interest",
    }
)

# Below this many anchors the sample is too small to act on.
MIN_ANCHORS = 8
# And the evidence has to be lopsided, not merely a majority.
MIN_RATIO = 0.8


def _tally(pairs: list[tuple[str, float]]) -> tuple[int, int, int, int]:
    """(income_wrong, income_total, expense_wrong, expense_total)."""
    income_wrong = income_total = 0
    expense_wrong = expense_total = 0
    for raw, amount in pairs:
        if not amount:
            continue
        if _INCOME_ANCHORS.search(raw or ""):
            income_total += 1
            if amount < 0:
                income_wrong += 1
            continue
        match = merchant_rules.lookup(descriptors.canonical_key(raw))
        if match and match.category in _EXPENSE_CATEGORIES:
            expense_total += 1
            if amount > 0:
                expense_wrong += 1
    return income_wrong, income_total, expense_wrong, expense_total


def detect_inverted(pairs: list[tuple[str, float]]) -> tuple[bool, str]:
    """Is this batch using money-out-is-positive? Returns (inverted, why)."""
    inc_wrong, inc_total, exp_wrong, exp_total = _tally(pairs)

    if inc_total >= MIN_ANCHORS and inc_wrong / inc_total >= MIN_RATIO:
        return True, (
            f"{inc_wrong}/{inc_total} payroll-type deposits were negative"
        )
    if exp_total >= MIN_ANCHORS and exp_wrong / exp_total >= MIN_RATIO:
        return True, (
            f"{exp_wrong}/{exp_total} known expense merchants were positive"
        )
    reason = (
        f"income anchors {inc_wrong}/{inc_total}, "
        f"expense anchors {exp_wrong}/{exp_total} — not enough evidence"
        if inc_total < MIN_ANCHORS and exp_total < MIN_ANCHORS
        else "signs look correct"
    )
    return False, reason


def repair_existing(conn) -> int:
    """Flip a whole database that was imported with inverted signs.

    Safe to run on every launch: after a flip the anchors read correctly, so it
    cannot fire twice. Nothing is written unless the evidence is lopsided, which
    is what keeps a correctly-signed file untouched.
    """
    rows = conn.execute(
        "SELECT raw_description, amount FROM transactions WHERE amount != 0"
    ).fetchall()
    if not rows:
        return 0
    pairs = [(r["raw_description"], float(r["amount"])) for r in rows]
    inverted, why = detect_inverted(pairs)
    if not inverted:
        return 0

    log.warning(
        "Amounts are inverted (%s) — negating %d transactions so income is "
        "positive. The previous file is backed up alongside the database.",
        why,
        len(rows),
    )
    conn.execute("UPDATE transactions SET amount = -amount")
    # Splits carry their own amounts and are stored in the same table, so the
    # blanket update already covers them. Category budgets are user-entered
    # positive limits and are deliberately left alone.
    conn.commit()
    return len(rows)
