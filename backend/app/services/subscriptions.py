"""Recurring-charge (subscription) detection — A3.

A pure heuristic over transaction history: group expense charges by merchant,
then flag merchants that recur at a regular cadence with a stable amount. No
LLM required. Produces the "Subscriptions: $X/mo" figure and a per-merchant
breakdown for the budget panel.
"""
from __future__ import annotations

import sqlite3
import statistics
from datetime import date

# Median gap (days) → cadence label + how many charges land in a month.
_CADENCES = [
    ("weekly", 5, 9, 30.44 / 7),
    ("biweekly", 12, 16, 30.44 / 14),
    ("monthly", 25, 35, 1.0),
    ("quarterly", 80, 100, 1 / 3),
    ("annual", 350, 385, 1 / 12),
]

MIN_OCCURRENCES = 3
# A charge counts toward a subscription if it is within this fraction of the
# merchant's median charge (subscriptions drift slightly with tax/tier changes).
AMOUNT_TOLERANCE = 0.20


def _parse(d: str) -> date | None:
    try:
        return date.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return None


def _classify(median_gap: float) -> tuple[str, float] | None:
    for label, lo, hi, per_month in _CADENCES:
        if lo <= median_gap <= hi:
            return label, per_month
    return None


def detect_subscriptions(conn: sqlite3.Connection) -> dict:
    """Return {items, total_monthly} of detected recurring charges.

    Only charges (negative amounts, non-split-parent) are considered. A merchant
    qualifies when it has >= 3 similarly-sized charges at a regular cadence.
    ``active`` marks subscriptions whose last charge is recent relative to the
    newest transaction on file; only active ones feed ``total_monthly``.
    """
    rows = conn.execute(
        "SELECT COALESCE(NULLIF(t.clean_merchant, ''), t.raw_description) AS merchant, "
        "t.date AS d, t.amount AS amount, "
        "c.name AS category, c.color AS color "
        "FROM transactions t LEFT JOIN categories c ON t.category_id = c.id "
        "WHERE t.is_split_parent = 0 AND t.amount < 0 AND t.date IS NOT NULL "
        "ORDER BY merchant, t.date"
    ).fetchall()

    groups: dict[str, list[sqlite3.Row]] = {}
    latest = None
    for r in rows:
        d = _parse(r["d"])
        if d is None:
            continue
        groups.setdefault(r["merchant"], []).append(r)
        if latest is None or d > latest:
            latest = d

    items: list[dict] = []
    for merchant, charges in groups.items():
        if len(charges) < MIN_OCCURRENCES:
            continue
        amounts = [abs(c["amount"]) for c in charges]
        median_amt = statistics.median(amounts)
        if median_amt <= 0:
            continue
        # Keep only charges close to the typical amount; require enough regulars.
        regular = [
            c
            for c in charges
            if abs(abs(c["amount"]) - median_amt) <= AMOUNT_TOLERANCE * median_amt
        ]
        if len(regular) < MIN_OCCURRENCES:
            continue

        dates = sorted(d for c in regular if (d := _parse(c["d"])) is not None)
        gaps = [
            (b - a).days
            for a, b in zip(dates, dates[1:], strict=False)
            if (b - a).days > 0
        ]
        if len(gaps) < MIN_OCCURRENCES - 1:
            continue
        median_gap = statistics.median(gaps)
        classified = _classify(median_gap)
        if classified is None:
            continue
        cadence, per_month = classified
        # Gaps must be reasonably consistent (not a coincidental clustering).
        if statistics.pstdev(gaps) > 0.5 * median_gap:
            continue

        typical = statistics.median([abs(c["amount"]) for c in regular])
        last_charge = dates[-1]
        active = latest is not None and (latest - last_charge).days <= 1.6 * median_gap
        items.append(
            {
                "merchant": merchant,
                "category": regular[0]["category"] or "Uncategorized",
                "color": regular[0]["color"] or "#64748b",
                "cadence": cadence,
                "amount": round(typical, 2),
                "monthly_cost": round(typical * per_month, 2),
                "occurrences": len(regular),
                "last_charge": last_charge.isoformat(),
                "active": active,
            }
        )

    items.sort(key=lambda i: i["monthly_cost"], reverse=True)
    total_monthly = round(sum(i["monthly_cost"] for i in items if i["active"]), 2)
    return {"items": items, "total_monthly": total_monthly}
