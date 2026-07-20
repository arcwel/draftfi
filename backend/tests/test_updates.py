"""F1 — desktop update check: version compare + soft-failing GitHub poll."""
from __future__ import annotations

import httpx
import pytest

from app.services import updates


def _reset_cache():
    updates._cache = None
    updates._cache_at = 0.0


def test_version_parse_and_compare():
    assert updates._parse_version("v0.3.1") == (0, 3, 1)
    assert updates._parse_version("1.2") == (1, 2)
    assert updates.is_newer("v0.3.0", "0.1.0") is True
    assert updates.is_newer("v0.1.0", "0.1.0") is False
    assert updates.is_newer("v0.0.9", "0.1.0") is False
    assert updates.is_newer("0.2.0", "0.1.9") is True


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, data=None, exc=None):
        self._data, self._exc = data, exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        if self._exc:
            raise self._exc
        return _FakeResp(self._data)


@pytest.mark.asyncio
async def test_check_reports_available_update(monkeypatch):
    _reset_cache()
    data = {"tag_name": "v9.9.9", "html_url": "https://example.com/releases/v9.9.9"}
    monkeypatch.setattr(
        updates.httpx, "AsyncClient", lambda *a, **k: _FakeClient(data=data)
    )
    out = await updates.check_for_update("0.1.0")
    assert out["latest"] == "v9.9.9"
    assert out["update_available"] is True
    assert out["url"] == "https://example.com/releases/v9.9.9"


@pytest.mark.asyncio
async def test_check_soft_fails_when_offline(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        updates.httpx,
        "AsyncClient",
        lambda *a, **k: _FakeClient(exc=httpx.ConnectError("no network")),
    )
    out = await updates.check_for_update("0.1.0")
    assert out["current"] == "0.1.0"
    assert out["update_available"] is False
    assert out["url"].startswith("https://github.com/")
