"""Phase 6.6 + 11.1 — API-level integration: branches, override, import flow.

Uses a real temp-file database so connections opened per request share state
(an in-memory DB would be private to each connection).
"""
from __future__ import annotations

import importlib
import time

import pytest
from fastapi.testclient import TestClient


def _run_import(client, content, filename="chase_checking.csv", account="Chase"):
    """Start an import and poll the background job to completion."""
    r = client.post(
        "/import/csv",
        files={"files": (filename, content, "text/csv")},
        data={"account_name": account},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    for _ in range(200):
        status = client.get(f"/import/status/{job_id}").json()
        if status["state"] in ("done", "error"):
            return status
        time.sleep(0.02)
    raise AssertionError("import did not finish in time")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_sandbox.db"
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(db_file))

    # Rebuild settings + app so the temp DB path takes effect.
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")
    importlib.reload(main)
    app = main.create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_categories_seeded(client):
    r = client.get("/categories")
    assert r.status_code == 200
    names = {c["name"] for c in r.json()}
    assert "Groceries" in names


def test_base_branch_is_editable_but_not_deletable(client):
    branches = client.get("/branches").json()
    base = next(b for b in branches if b["is_base"])
    # The base is the user's real baseline — it can be edited...
    r = client.patch(
        f"/branches/{base['id']}",
        json={"parameters": {"starting_assets": 12000, "monthly_inflow": 4000}},
    )
    assert r.status_code == 200
    assert r.json()["parameters"]["starting_assets"] == 12000
    # ...but it cannot be deleted.
    assert client.delete(f"/branches/{base['id']}").status_code == 403


def test_reset_clears_data_but_keeps_categories(client, monkeypatch):
    from app.services import llm

    async def offline(config):
        return False, None, "offline"

    monkeypatch.setattr(llm, "health", offline)

    from pathlib import Path

    sample = (
        Path(__file__).resolve().parent.parent / "sample_data" / "chase_checking.csv"
    ).read_bytes()
    _run_import(client, sample)
    # Give the base plan some values and a sandbox branch.
    base = next(b for b in client.get("/branches").json() if b["is_base"])
    client.patch(f"/branches/{base['id']}", json={"parameters": {"starting_assets": 99}})
    client.post("/branches", json={"name": "Scratch"})
    assert client.get("/transactions").json()["total"] > 0

    r = client.post("/reset")
    assert r.status_code == 200
    assert client.get("/transactions").json()["total"] == 0
    branches = client.get("/branches").json()
    assert len(branches) == 1 and branches[0]["is_base"]
    assert branches[0]["parameters"]["starting_assets"] == 0
    # Categories survive a reset.
    assert any(c["name"] == "Groceries" for c in client.get("/categories").json())


def test_branch_lifecycle_and_immutability(client):
    # Duplicate from base.
    created = client.post("/branches", json={"name": "Aggressive Save"})
    assert created.status_code == 201
    branch = created.json()
    assert branch["is_base"] is False

    # Mutate the sandbox branch.
    r = client.patch(
        f"/branches/{branch['id']}",
        json={"parameters": {"income_adjustment_pct": 15, "starting_cash": 5000}},
    )
    assert r.status_code == 200
    assert r.json()["parameters"]["income_adjustment_pct"] == 15

    # Base remains untouched.
    base = next(b for b in client.get("/branches").json() if b["is_base"])
    assert base["parameters"].get("income_adjustment_pct", 0) == 0

    # Delete the branch.
    assert client.delete(f"/branches/{branch['id']}").status_code == 204
    assert all(b["id"] != branch["id"] for b in client.get("/branches").json())


def test_compare_returns_base_and_branch(client):
    branch = client.post("/branches", json={"name": "Compare Me"}).json()
    client.patch(
        f"/branches/{branch['id']}",
        json={"parameters": {"starting_cash": 1000, "monthly_inflow": 100,
                             "monthly_outflow": 50, "runway_months": 24}},
    )
    r = client.get(f"/branches/{branch['id']}/compare")
    assert r.status_code == 200
    body = r.json()
    assert "base" in body and "branch" in body
    assert len(body["branch"]["runway"]) == 25


def test_import_and_override_flow(client, monkeypatch):
    # Force graceful-degradation path so the test needs no live LLM.
    from app.services import llm

    async def offline(config):
        return False, None, "no llm in test"

    monkeypatch.setattr(llm, "health", offline)

    from pathlib import Path

    sample = (
        Path(__file__).resolve().parent.parent / "sample_data" / "chase_checking.csv"
    ).read_bytes()
    result = _run_import(client, sample)
    assert result["imported"] == 6
    assert result["uncategorized"] == 6  # LLM offline -> all uncategorized

    # Re-import identical file -> all deduped.
    result2 = _run_import(client, sample)
    assert result2["skipped_duplicates"] == 6

    # Override a category and confirm it propagates + caches.
    txs = client.get("/transactions").json()["items"]
    target = next(t for t in txs if "NETFLIX" in t["raw_description"])
    cats = client.get("/categories").json()
    ent = next(c for c in cats if c["name"] == "Entertainment")
    patched = client.patch(
        f"/transactions/{target['id']}/category", json={"category_id": ent["id"]}
    )
    assert patched.status_code == 200
    assert patched.json()["category_name"] == "Entertainment"
    assert patched.json()["resolution"] == "override"
