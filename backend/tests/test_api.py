"""Phase 6.6 + 11.1 — API-level integration: branches, override, import flow.

Uses a real temp-file database so connections opened per request share state
(an in-memory DB would be private to each connection).
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


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


def test_base_branch_exists_and_immutable(client):
    branches = client.get("/branches").json()
    base = next(b for b in branches if b["is_base"])
    # Base cannot be mutated.
    r = client.patch(f"/branches/{base['id']}", json={"name": "Hacked"})
    assert r.status_code == 403


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
    r = client.post(
        "/import/csv",
        files={"file": ("chase_checking.csv", sample, "text/csv")},
        data={"account_name": "Chase Checking"},
    )
    assert r.status_code == 200
    result = r.json()
    assert result["imported"] == 6
    assert result["uncategorized"] == 6  # LLM offline -> all uncategorized

    # Re-import identical file -> all deduped.
    r2 = client.post(
        "/import/csv",
        files={"file": ("chase_checking.csv", sample, "text/csv")},
        data={"account_name": "Chase Checking"},
    )
    assert r2.json()["skipped_duplicates"] == 6

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
