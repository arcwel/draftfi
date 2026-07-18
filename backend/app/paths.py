"""Cross-platform per-user application data locations.

Used by the packaged desktop app so the database and config persist in the
conventional place for each OS (and where the user always has write access).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DraftFi"


def user_data_dir() -> Path:
    """Return the per-user data directory for DraftFi, creating it."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:  # Linux / other
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> Path:
    return user_data_dir() / "sandbox.db"
