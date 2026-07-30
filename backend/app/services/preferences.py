"""User display preferences (G4) — currency + locale for number formatting.

Persisted in ``app_settings`` and consumed by the frontend's shared ``format``
helper so the hardcoded USD/en-US in the UI becomes one setting.
"""
from __future__ import annotations

import json
import sqlite3

from app.db import repository as repo

K_CURRENCY = "currency"
K_LOCALE = "locale"
K_TEXT_SCALE = "text_scale"
# Ledger column widths in px, keyed by column id. Stored as JSON because it is
# opaque layout state the backend has no reason to model any further; the
# frontend owns which columns exist and clamps anything it reads back.
K_LEDGER_COLUMNS = "ledger_columns"
DEFAULT_CURRENCY = "USD"
DEFAULT_LOCALE = "en-US"
# Points added to the 16px base font size (0-10). The frontend scales the root
# font size, so every rem-based size in the UI grows proportionally.
DEFAULT_TEXT_SCALE = 0
MAX_TEXT_SCALE = 10


def _read_scale(conn: sqlite3.Connection) -> int:
    raw = repo.get_setting(conn, K_TEXT_SCALE)
    try:
        return max(0, min(MAX_TEXT_SCALE, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_TEXT_SCALE


# Wide enough for a pathological bank descriptor, narrow enough that nothing
# stored here can render an unusable table. Mirrors lib/ledgerColumns.js.
MIN_COLUMN_WIDTH = 40
MAX_COLUMN_WIDTH = 900


def _read_ledger_columns(conn: sqlite3.Connection) -> dict[str, int]:
    """Stored column widths, or {} when unset/unreadable.

    Never raises: a malformed row (older build, hand-edited DB) must degrade to
    the frontend's defaults rather than break the preferences endpoint that the
    whole UI boots through.
    """
    raw = repo.get_setting(conn, K_LEDGER_COLUMNS)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    widths: dict[str, int] = {}
    for key, value in parsed.items():
        try:
            px = int(value)
        except (TypeError, ValueError):
            continue
        widths[str(key)] = max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, px))
    return widths


def get_preferences(conn: sqlite3.Connection) -> dict:
    return {
        "currency": repo.get_setting(conn, K_CURRENCY) or DEFAULT_CURRENCY,
        "locale": repo.get_setting(conn, K_LOCALE) or DEFAULT_LOCALE,
        "text_scale": _read_scale(conn),
        "ledger_columns": _read_ledger_columns(conn),
    }


def set_preferences(
    conn: sqlite3.Connection,
    currency: str | None = None,
    locale: str | None = None,
    text_scale: int | None = None,
    ledger_columns: dict[str, int] | None = None,
) -> dict:
    if currency:
        repo.set_setting(conn, K_CURRENCY, currency.strip())
    if locale:
        repo.set_setting(conn, K_LOCALE, locale.strip())
    if text_scale is not None:
        clamped = max(0, min(MAX_TEXT_SCALE, int(text_scale)))
        repo.set_setting(conn, K_TEXT_SCALE, str(clamped))
    if ledger_columns is not None:
        widths = {
            str(key): max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, int(px)))
            for key, px in ledger_columns.items()
        }
        repo.set_setting(conn, K_LEDGER_COLUMNS, json.dumps(widths, sort_keys=True))
    return get_preferences(conn)
