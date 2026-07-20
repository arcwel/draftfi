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


def test_branch_persists_change_events(client):
    """E2: change events round-trip through branch storage."""
    branch = client.post("/branches", json={"name": "Raise"}).json()
    r = client.patch(
        f"/branches/{branch['id']}",
        json={
            "events": [
                {"label": "Promotion", "kind": "income", "mode": "set",
                 "amount": 8000, "month": 6}
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["events"][0]["amount"] == 8000
    # Re-fetch to confirm persistence.
    reload = next(b for b in client.get("/branches").json() if b["id"] == branch["id"])
    assert reload["events"][0]["label"] == "Promotion"


def test_scenarios_compare_delta_table(client):
    """E4: base + branches overlay with a delta table anchored on the base."""
    base = next(b for b in client.get("/branches").json() if b["is_base"])
    client.patch(
        f"/branches/{base['id']}",
        json={"parameters": {"starting_cash": 1000, "monthly_inflow": 100,
                             "monthly_outflow": 100, "runway_months": 72}},
    )
    branch = client.post("/branches", json={"name": "Save More"}).json()
    client.patch(
        f"/branches/{branch['id']}",
        json={"parameters": {"starting_cash": 1000, "monthly_inflow": 300,
                             "monthly_outflow": 100, "runway_months": 72}},
    )
    r = client.post("/scenarios/compare", json={"branch_ids": [branch["id"]]})
    assert r.status_code == 200
    body = r.json()
    # Base is always first; requested branch follows.
    assert body["scenarios"][0]["is_base"] is True
    assert len(body["scenarios"]) == 2
    assert body["checkpoints"] == [12, 36, 72]
    # At month 12 the higher-income branch beats the flat base.
    row12 = next(d for d in body["deltas"] if d["month"] == 12)
    branch_cell = next(c for c in row12["cells"] if not c["is_base"])
    assert branch_cell["cash_delta"] > 0


def test_goals_crud_and_validation(client):
    """E5: goal create / list / update / delete."""
    created = client.post(
        "/goals",
        json={"label": "House down payment", "kind": "cash",
              "target_amount": 40000, "target_month": 24},
    )
    assert created.status_code == 201
    goal = created.json()
    assert goal["kind"] == "cash"

    assert len(client.get("/goals").json()) == 1

    upd = client.patch(f"/goals/{goal['id']}", json={"target_amount": 50000})
    assert upd.status_code == 200
    assert upd.json()["target_amount"] == 50000

    assert client.delete(f"/goals/{goal['id']}").status_code == 204
    assert client.get("/goals").json() == []
    assert client.patch(f"/goals/{goal['id']}", json={"label": "x"}).status_code == 404


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


# --------------------------------------------------------------------------- #
# Batch A — LLM provider surface (A1/A2) + analytics endpoints (A3/A4)
# --------------------------------------------------------------------------- #
def test_llm_test_unknown_provider_400(client):
    r = client.post("/llm/test", json={"provider": "bogus"})
    assert r.status_code == 400


def test_llm_test_unreachable_returns_not_ok(client):
    # A1: a dead endpoint reports ok=false with a detail, not an exception.
    r = client.post(
        "/llm/test",
        json={"provider": "ollama", "base_url": "http://127.0.0.1:1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["detail"]


def test_llm_models_unreachable_returns_empty(client):
    # A2: unreachable provider -> empty list + detail (client falls back to text).
    r = client.post(
        "/llm/models",
        json={"provider": "ollama", "base_url": "http://127.0.0.1:1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["models"] == []
    assert body["detail"]


def test_subscriptions_and_insights_smoke(client):
    # A3/A4: endpoints respond with empty structures on an empty database.
    subs = client.get("/subscriptions")
    assert subs.status_code == 200
    assert subs.json() == {"items": [], "total_monthly": 0.0}

    ins = client.get("/insights")
    assert ins.status_code == 200
    assert ins.json() == {"insights": []}


def test_narrative_empty_history_is_graceful(client):
    # A4: with no history there are no insights, so the narrative short-circuits
    # to a friendly message without needing a provider (no 500).
    r = client.post("/insights/narrative")
    assert r.status_code == 200
    assert "history" in r.json()["narrative"].lower()
