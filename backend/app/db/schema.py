"""SQLite schema, migrations, and default seed data.

The database is intentionally driven by hand-written SQL (no ORM) to keep the
local-first footprint tiny and the schema transparent for an open-source
audience. Migrations are tracked in a ``schema_migrations`` table and applied
idempotently on startup.
"""
from __future__ import annotations

import json
import sqlite3

# The Base Plan starts empty: no cash, no assets, no debt. Net worth begins at
# $0 and the forecasts stay flat until the user imports transactions or enters
# their own numbers. monthly_inflow/outflow stay null so they derive from
# imported history until manually overridden. Only chart horizons and growth
# rates carry non-zero defaults (they're display settings, not "your data").
BASE_PLAN_PARAMETERS: dict = {
    "starting_cash": 0,
    "monthly_inflow": None,
    "monthly_outflow": None,
    "income_adjustment_pct": 0,
    "safety_floor": 0,
    "runway_months": 36,
    "macro_years": 10,
    "annual_return_pct": 6,
    "annual_debt_rate_pct": 5,
    "starting_assets": 0,
    "starting_debt": 0,
}

# Ordered list of (version, description, sql) migrations. Append-only:
# never edit a migration that has shipped — add a new one instead.
MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "initial schema: categories, merchant_llm_cache, transactions",
        """
        CREATE TABLE IF NOT EXISTS categories (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#64748B'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_name ON categories(name);

        CREATE TABLE IF NOT EXISTS merchant_llm_cache (
            raw_description TEXT PRIMARY KEY,
            clean_merchant  TEXT NOT NULL,
            category_id     INTEGER,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cache_raw ON merchant_llm_cache(raw_description);

        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT NOT NULL,
            raw_description TEXT NOT NULL,
            amount          REAL NOT NULL,
            account_name    TEXT NOT NULL,
            category_id     INTEGER,
            clean_merchant  TEXT,
            resolution      TEXT,   -- cache | llm | override | uncategorized
            import_hash     TEXT,   -- dedupe key for re-imported statements
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tx_raw ON transactions(raw_description);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_import_hash
            ON transactions(import_hash);
        """,
    ),
    (
        2,
        "sandbox branches: financial-state containers",
        """
        CREATE TABLE IF NOT EXISTS branches (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            is_base      INTEGER NOT NULL DEFAULT 0,   -- exactly one protected base
            parameters   TEXT NOT NULL DEFAULT '{}',   -- JSON: assumptions + params
            milestones   TEXT NOT NULL DEFAULT '[]',   -- JSON array of milestones
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_branches_is_base ON branches(is_base);
        """,
    ),
    (
        3,
        "app_settings: local key-value store (LLM provider config + API keys)",
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """,
    ),
    (
        4,
        "budget targets: optional monthly limit per category",
        """
        ALTER TABLE categories ADD COLUMN monthly_budget REAL;
        """,
    ),
    (
        5,
        "ledger depth: split transactions, notes, and tags",
        """
        -- A split parent keeps its row (and import_hash for dedupe) but is
        -- excluded from aggregations; its children carry the amounts.
        ALTER TABLE transactions ADD COLUMN parent_tx_id INTEGER
            REFERENCES transactions(id) ON DELETE CASCADE;
        ALTER TABLE transactions ADD COLUMN is_split_parent INTEGER
            NOT NULL DEFAULT 0;
        ALTER TABLE transactions ADD COLUMN note TEXT;
        ALTER TABLE transactions ADD COLUMN tags TEXT;  -- JSON array of strings
        CREATE INDEX IF NOT EXISTS idx_tx_parent ON transactions(parent_tx_id);
        """,
    ),
]

# Default budget categories with visualization colors (Tailwind-ish hexes).
DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Income", "#22C55E"),
    ("Housing", "#3B82F6"),
    ("Groceries", "#10B981"),
    ("Dining", "#F59E0B"),
    ("Transportation", "#6366F1"),
    ("Utilities", "#0EA5E9"),
    ("Software Subscriptions", "#8B5CF6"),
    ("Entertainment", "#EC4899"),
    ("Healthcare", "#EF4444"),
    ("Shopping", "#F97316"),
    ("Travel", "#14B8A6"),
    ("Savings & Investments", "#84CC16"),
    ("Fees & Interest", "#A855F7"),
    ("Uncategorized", "#64748B"),
]


def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, description TEXT, applied_at TEXT "
        "DEFAULT (datetime('now')))"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return row[0] or 0


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply any pending migrations in a single transaction per migration."""
    current = _current_version(conn)
    for version, description, sql in MIGRATIONS:
        if version <= current:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
            (version, description),
        )
        conn.commit()


def seed_defaults(conn: sqlite3.Connection) -> None:
    """Insert default categories and a protected Base Plan if missing."""
    for name, color in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, color) VALUES (?, ?)",
            (name, color),
        )
    base = conn.execute("SELECT id FROM branches WHERE is_base = 1").fetchone()
    if base is None:
        conn.execute(
            "INSERT INTO branches (name, is_base, parameters, milestones) "
            "VALUES ('Base Plan', 1, ?, '[]')",
            (json.dumps(BASE_PLAN_PARAMETERS),),
        )
    conn.commit()


def initialize(conn: sqlite3.Connection) -> None:
    """Full bootstrap: schema migrations followed by default seed data."""
    conn.execute("PRAGMA foreign_keys = ON")
    apply_migrations(conn)
    seed_defaults(conn)
