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

Four rules keep this from doing damage, each of which exists because the
previous version of this module got it wrong:

1. **Per account, never globally.** A checking export and a card export can
   disagree about the convention and both be internally consistent. Tallying
   them together let a card's positive charges outvote checking's correct
   payroll, so importing two files at once corrupted the good one. Every
   decision here is scoped to one ``account_name``.

2. **Either signal can fire, but neither may contradict.** The old code checked
   income anchors first and expense anchors second and acted on whichever spoke
   up. When the two disagreed, each flip made the *other* one fire — so the
   whole database inverted itself on every launch, forever. A signal that
   strongly says "these signs are correct" now vetoes the other.

3. **Refunds and reinvestments are not evidence.** A refund from an expense
   merchant is positive *and correct*; a reinvested dividend is negative *and
   correct*. Counting them as errors made a refund-heavy month look inverted.

4. **The repair runs once.** ``repair_existing`` is a migration, not a
   safeguard. Import-time normalization handles new data.

When the evidence is not lopsided the amounts are left exactly as they came in —
guessing at the direction of someone's money is worse than leaving it alone.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable

from app.services import descriptors, merchant_rules

log = logging.getLogger("draftfi.signs")

# Set once the whole-database repair has run. It is a one-time correction for
# data imported before sign normalization existed, not a recurring safety net.
SIGNS_REPAIR_FLAG = "signs_repair_v1"

# Money-in by definition. Narrower than merchant_rules' income patterns: this
# list must contain nothing whose direction is arguable.
_INCOME_ANCHORS = re.compile(
    r"\b(PAYROLL|DIRECT DEP|DIR DEP|SALARY|PAYCHECK|INTEREST PAID|"
    r"DIVIDEND|TAX REF|IRS TREAS|SSA TREAS)\b",
    re.IGNORECASE,
)

# A refund, return or reversal legitimately runs against its merchant's normal
# direction, so it says nothing about the file's convention. Same for a dividend
# that is reinvested rather than paid out — the word DIVIDEND is there, but the
# money is going out, correctly.
_NOT_EVIDENCE = re.compile(
    r"\b(REFUND|RETURN|RETURNED|REVERSAL|REVERSED|CHARGEBACK|CREDIT MEMO|"
    r"ADJUSTMENT|ADJ|DISPUTE|REINVEST|REINVESTMENT|CASH DIVIDEND REINVEST)\b",
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
# And the evidence has to be overwhelming, not merely lopsided. At 0.8 a run of
# refunds could outvote the real charges; 0.9 needs nine in ten to be wrong.
MIN_RATIO = 0.9
# The mirror of MIN_RATIO: at or below this, a signal is asserting the file is
# already correct, and it gets to veto the other signal.
VETO_RATIO = 1.0 - MIN_RATIO


class Tally:
    """Anchor counts for one account."""

    __slots__ = ("income_wrong", "income_total", "expense_wrong", "expense_total")

    def __init__(self) -> None:
        self.income_wrong = self.income_total = 0
        self.expense_wrong = self.expense_total = 0

    def add(self, raw: str, amount: float) -> None:
        if not amount:
            return
        text = raw or ""
        if _NOT_EVIDENCE.search(text):
            return
        key = descriptors.canonical_key(text)
        # A card payment or an internal move is not directional evidence: it is
        # negative on one side and positive on the other, both correctly.
        is_flow = merchant_rules.classify_flow(key) is not None
        if is_flow and not _INCOME_ANCHORS.search(text):
            return
        if _INCOME_ANCHORS.search(text):
            self.income_total += 1
            if amount < 0:
                self.income_wrong += 1
            return
        match = merchant_rules.lookup(key)
        if match and match.category in _EXPENSE_CATEGORIES:
            self.expense_total += 1
            if amount > 0:
                self.expense_wrong += 1

    def _ratio(self, wrong: int, total: int) -> float:
        return wrong / total if total else 0.0

    def verdict(self) -> tuple[bool, str]:
        """(inverted, why) for this account."""
        inc_n, exp_n = self.income_total, self.expense_total
        inc_r = self._ratio(self.income_wrong, inc_n)
        exp_r = self._ratio(self.expense_wrong, exp_n)

        inc_fires = inc_n >= MIN_ANCHORS and inc_r >= MIN_RATIO
        exp_fires = exp_n >= MIN_ANCHORS and exp_r >= MIN_RATIO
        inc_vetoes = inc_n >= MIN_ANCHORS and inc_r <= VETO_RATIO
        exp_vetoes = exp_n >= MIN_ANCHORS and exp_r <= VETO_RATIO

        if (inc_fires or exp_fires) and (inc_vetoes or exp_vetoes):
            # The two signals disagree. Flipping would fix one and break the
            # other, and next launch the other would ask to flip it back.
            return False, (
                f"signals disagree (payroll {self.income_wrong}/{inc_n} negative, "
                f"expense merchants {self.expense_wrong}/{exp_n} positive) — "
                "left alone"
            )
        if inc_fires:
            return True, (
                f"{self.income_wrong}/{inc_n} payroll-type deposits were negative"
            )
        if exp_fires:
            return True, (
                f"{self.expense_wrong}/{exp_n} known expense merchants "
                "were positive"
            )
        if inc_n < MIN_ANCHORS and exp_n < MIN_ANCHORS:
            return False, (
                f"income anchors {self.income_wrong}/{inc_n}, "
                f"expense anchors {self.expense_wrong}/{exp_n} — not enough evidence"
            )
        return False, "signs look correct"


def detect_inverted(pairs: Iterable[tuple[str, float]]) -> tuple[bool, str]:
    """Is this batch using money-out-is-positive? Returns (inverted, why).

    Treats the batch as one account. Callers holding multi-account data should
    use :func:`plan_flips` instead — see rule 1 in the module docstring.
    """
    tally = Tally()
    for raw, amount in pairs:
        tally.add(raw, amount)
    return tally.verdict()


def plan_flips(
    rows: Iterable[tuple[str, str, float]],
) -> dict[str, tuple[bool, str]]:
    """Decide per account. ``rows`` is (account_name, raw_description, amount)."""
    tallies: dict[str, Tally] = defaultdict(Tally)
    for account, raw, amount in rows:
        tallies[account or ""].add(raw, amount)
    return {account: t.verdict() for account, t in tallies.items()}


def repair_existing(conn) -> int:
    """One-time correction of a database imported with inverted signs.

    Runs once and records that it has, because it is a migration for data that
    predates import-time normalization — not a recurring check. Re-running it
    would fight with anything the user corrected by hand afterwards, and an
    earlier version that did re-run inverted the whole file on every launch.

    Returns the number of transactions negated.
    """
    done = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (SIGNS_REPAIR_FLAG,)
    ).fetchone()
    if done and done[0]:
        return 0

    rows = conn.execute(
        "SELECT account_name, raw_description, amount FROM transactions "
        "WHERE amount != 0"
    ).fetchall()
    if not rows:
        # Nothing to judge. Deliberately do NOT mark the repair done: a fresh
        # install has no data yet, and flagging it here would permanently skip
        # the repair for every user who opens the app before importing.
        return 0

    plan = plan_flips(
        [(r["account_name"], r["raw_description"], float(r["amount"])) for r in rows]
    )

    flipped = 0
    for account, (inverted, why) in sorted(plan.items()):
        if not inverted:
            log.info("Account %r sign check: %s", account or "(unnamed)", why)
            continue
        cur = conn.execute(
            "UPDATE transactions SET amount = -amount "
            "WHERE COALESCE(account_name, '') = ?",
            (account,),
        )
        flipped += cur.rowcount
        log.warning(
            "Account %r amounts are inverted (%s) — negated %d transactions so "
            "income is positive.",
            account or "(unnamed)",
            why,
            cur.rowcount,
        )

    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, '1') "
        "ON CONFLICT(key) DO UPDATE SET value = '1'",
        (SIGNS_REPAIR_FLAG,),
    )
    conn.commit()
    return flipped
