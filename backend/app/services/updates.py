"""In-app update check (F1).

Asks the GitHub Releases API for the latest published tag and compares it to the
running version. Done server-side so the browser never hits GitHub directly
(no CORS, and the result can be cached). Every failure path is soft: if GitHub
is unreachable or rate-limits us, we simply report "no update available".
"""
from __future__ import annotations

import re
import time

import httpx

from app import __version__

GITHUB_REPO = "arcwel/draftfi"
_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"

# Cache the result so repeated calls (or a chatty client) don't hammer GitHub.
_CACHE_TTL = 3600.0  # seconds
_cache: dict | None = None
_cache_at: float = 0.0

_VER_RE = re.compile(r"(\d+)")


def _parse_version(tag: str) -> tuple[int, ...]:
    """Turn ``v0.3.1`` / ``0.3.1`` into a comparable numeric tuple."""
    nums = _VER_RE.findall(tag or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    """True when ``latest`` is a strictly higher version than ``current``."""
    return _parse_version(latest) > _parse_version(current)


async def check_for_update(current: str = __version__) -> dict:
    """Return {current, latest, update_available, url}. Never raises."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL:
        return _cache

    result = {
        "current": current,
        "latest": None,
        "update_available": False,
        "url": _RELEASES_PAGE,
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                _RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            data = resp.json()
        latest = data.get("tag_name")
        if latest:
            result["latest"] = latest
            result["update_available"] = is_newer(latest, current)
            result["url"] = data.get("html_url") or _RELEASES_PAGE
    except (httpx.HTTPError, ValueError, KeyError):
        # Offline / rate-limited / no releases yet — leave the soft default.
        pass

    _cache, _cache_at = result, now
    return result
