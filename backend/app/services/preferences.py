"""User display preferences (G4) — currency + locale for number formatting.

Persisted in ``app_settings`` and consumed by the frontend's shared ``format``
helper so the hardcoded USD/en-US in the UI becomes one setting.
"""
from __future__ import annotations

import sqlite3

from app.db import repository as repo

K_CURRENCY = "currency"
K_LOCALE = "locale"
K_TEXT_SCALE = "text_scale"
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


def get_preferences(conn: sqlite3.Connection) -> dict:
    return {
        "currency": repo.get_setting(conn, K_CURRENCY) or DEFAULT_CURRENCY,
        "locale": repo.get_setting(conn, K_LOCALE) or DEFAULT_LOCALE,
        "text_scale": _read_scale(conn),
    }


def set_preferences(
    conn: sqlite3.Connection,
    currency: str | None = None,
    locale: str | None = None,
    text_scale: int | None = None,
) -> dict:
    if currency:
        repo.set_setting(conn, K_CURRENCY, currency.strip())
    if locale:
        repo.set_setting(conn, K_LOCALE, locale.strip())
    if text_scale is not None:
        clamped = max(0, min(MAX_TEXT_SCALE, int(text_scale)))
        repo.set_setting(conn, K_TEXT_SCALE, str(clamped))
    return get_preferences(conn)
