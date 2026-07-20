"""User display preferences (G4) — currency + locale for number formatting.

Persisted in ``app_settings`` and consumed by the frontend's shared ``format``
helper so the hardcoded USD/en-US in the UI becomes one setting.
"""
from __future__ import annotations

import sqlite3

from app.db import repository as repo

K_CURRENCY = "currency"
K_LOCALE = "locale"
DEFAULT_CURRENCY = "USD"
DEFAULT_LOCALE = "en-US"


def get_preferences(conn: sqlite3.Connection) -> dict:
    return {
        "currency": repo.get_setting(conn, K_CURRENCY) or DEFAULT_CURRENCY,
        "locale": repo.get_setting(conn, K_LOCALE) or DEFAULT_LOCALE,
    }


def set_preferences(
    conn: sqlite3.Connection,
    currency: str | None = None,
    locale: str | None = None,
) -> dict:
    if currency:
        repo.set_setting(conn, K_CURRENCY, currency.strip())
    if locale:
        repo.set_setting(conn, K_LOCALE, locale.strip())
    return get_preferences(conn)
