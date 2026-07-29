"""Application logging: a rotating file the user can actually hand over.

Before this existed DraftFi wrote nothing anywhere — a packaged build that
misbehaved left the user with no artifact to attach to a bug report, and the
uvicorn access log (the one place a failing request would have shown up) was
suppressed by ``log_level="warning"``. Diagnosing anything meant launching the
frozen app by hand and curling its API.

Logs land next to the database in the per-user app-data directory, so they
persist across launches and are always writable:

* macOS   — ``~/Library/Application Support/DraftFi/logs/draftfi.log``
* Windows — ``%APPDATA%\\DraftFi\\logs\\draftfi.log``
* Linux   — ``$XDG_DATA_HOME/DraftFi/logs/draftfi.log``

**Secrets never reach the file.** Some providers (Gemini) carry the API key in
the URL query string, and uvicorn's access log prints the full path — so an
unfiltered access log would write the user's key to disk in plaintext on every
single request. :class:`RedactFilter` is installed on every handler to strip
them, and it is applied to the formatted message *and* the raw args.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
from pathlib import Path

from app.paths import user_data_dir

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "draftfi.log"

# Keep ~5 MB of history total: enough to cover a long sync plus the launch that
# preceded it, small enough to attach to an email.
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# ``?key=<secret>`` / ``&key=<secret>`` (Gemini), plus bearer tokens and the
# Anthropic header style, in case a library ever echoes one into a message.
_REDACTIONS: tuple[re.Pattern[str], str] = (
    (re.compile(r"([?&]key=)[^&\s'\"]+"), r"\1REDACTED"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE), r"\1REDACTED"),
    (
        re.compile(
            r"(x-api-key['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9._\-]+", re.IGNORECASE
        ),
        r"\1REDACTED",
    ),
    (re.compile(r"\b(sk-[A-Za-z0-9]{4})[A-Za-z0-9._\-]{8,}"), r"\1REDACTED"),
    (re.compile(r"\b(AIza)[A-Za-z0-9._\-]{20,}"), r"\1REDACTED"),
)

_configured = False


def redact(text: str) -> str:
    """Strip anything that looks like a credential out of ``text``."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RedactFilter(logging.Filter):
    """Scrub credentials from a record before any handler writes it.

    uvicorn's access logger formats the request path via ``record.args``, so
    redacting only ``record.msg`` would miss the query string entirely — the
    exact place Gemini keys live. Both are handled.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def log_dir() -> Path:
    path = user_data_dir() / LOG_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return log_dir() / LOG_FILE_NAME


def log_files() -> list[Path]:
    """Current log plus rotated siblings, newest first."""
    directory = log_dir()
    if not directory.is_dir():
        return []
    files = [p for p in directory.iterdir() if p.name.startswith(LOG_FILE_NAME)]
    return sorted(files, key=lambda p: p.name)


def setup_logging(level: int | str | None = None) -> Path:
    """Install the rotating file handler + console handler. Idempotent.

    Returns the log file path. Set ``DRAFTFI_LOG_LEVEL`` to override the level
    (default INFO); the file is always written even when the console is quiet.
    """
    global _configured
    path = log_path()
    if _configured:
        return path

    if level is None:
        level = os.environ.get("DRAFTFI_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    redactor = RedactFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(redactor)

    root = logging.getLogger()
    root.setLevel(level)
    # Replace our own handlers on re-entry (e.g. reload) without stomping on
    # anything a host application installed.
    for existing in list(root.handlers):
        if getattr(existing, "_draftfi", False):
            root.removeHandler(existing)
    for handler in (file_handler, console):
        handler._draftfi = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    # uvicorn installs its own handlers and disables propagation; route them
    # through ours so requests (including the 404s we care about) hit the file.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)

    # httpx logs every request at INFO with the full URL — redacted by the
    # filter, but still noisy for a desktop app. Keep it at WARNING.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _configured = True
    logging.getLogger("draftfi").info("Logging to %s", path)
    return path
