"""Manual transaction CRUD, export/backup/restore, NL scenario parsing,
and batched categorization."""
from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "feat.db"
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(db_file))
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")
    importlib.reload(main)
    with TestClient(main.create_app()) as c:
        yield c


# --------------------------------------------------------------------------- #
# Manual transaction CRUD
# --------------------------------------------------------------------------- #
def test_manual_transaction_lifecycle(client):
    cats = client.get("/categories").json()
    dining = next(c for c in cats if c["name"] == "Dining")

    created = client.post(
        "/transactions",
        json={"date": "2026-07-01", "amount": -14.5,
              "raw_description": "Cash — food truck", "category_id": dining["id"]},
    )
    assert created.status_code == 201
    tx = created.json()
    assert tx["resolution"] == "manual"
    assert tx["category_name"] == "Dining"

    # Edit the amount and date.
    patched = client.patch(
        f"/transactions/{tx['id']}", json={"amount": -16.0, "date": "2026-07-02"}
    )
    assert patched.status_code == 200
    assert patched.json()["amount"] == -16.0
    assert patched.json()["date"] == "2026-07-02"

    # Two identical manual entries are both legitimate (no dedupe clash).
    dup = client.post(
        "/transactions",
        json={"date": "2026-07-02", "amount": -16.0,
              "raw_description": "Cash — food truck"},
    )
    assert dup.status_code == 201
    assert client.get("/transactions").json()["total"] == 2

    # Delete one.
    assert client.delete(f"/transactions/{tx['id']}").status_code == 204
    assert client.get("/transactions").json()["total"] == 1
    assert client.delete(f"/transactions/{tx['id']}").status_code == 404


def test_manual_transaction_defaults_to_uncategorized(client):
    created = client.post(
        "/transactions",
        json={"date": "2026-07-01", "amount": -5, "raw_description": "Mystery"},
    ).json()
    assert created["category_name"] == "Uncategorized"


# --------------------------------------------------------------------------- #
# Export / backup / restore
# --------------------------------------------------------------------------- #
def test_export_csv_and_json(client):
    client.post(
        "/transactions",
        json={"date": "2026-07-01", "amount": -9.99,
              "raw_description": "SPOTIFY USA"},
    )
    csv_resp = client.get("/export/transactions.csv")
    assert csv_resp.status_code == 200
    assert "SPOTIFY USA" in csv_resp.text
    assert csv_resp.headers["content-disposition"].startswith("attachment")

    json_resp = client.get("/export/data.json")
    assert json_resp.status_code == 200
    data = json_resp.json()
    assert len(data["transactions"]) == 1
    assert any(c["name"] == "Groceries" for c in data["categories"])
    assert any(b["is_base"] for b in data["branches"])


def test_backup_download_and_restore_roundtrip(client, tmp_path):
    client.post(
        "/transactions",
        json={"date": "2026-07-01", "amount": -42,
              "raw_description": "KEEP ME"},
    )
    backup = client.get("/export/backup.db")
    assert backup.status_code == 200
    assert backup.content.startswith(b"SQLite format 3\x00")

    # Wipe, then restore the backup — data comes back.
    client.post("/reset")
    assert client.get("/transactions").json()["total"] == 0
    restored = client.post(
        "/export/restore",
        files={"file": ("backup.db", backup.content, "application/octet-stream")},
    )
    assert restored.status_code == 200
    assert restored.json()["transactions"] == 1
    assert client.get("/transactions").json()["total"] == 1


def test_restore_rejects_non_draftfi_files(client):
    r = client.post(
        "/export/restore",
        files={"file": ("evil.db", b"definitely not sqlite", "application/octet-stream")},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Natural-language scenario parsing
# --------------------------------------------------------------------------- #
def test_scenario_parse_returns_validated_milestones(client, monkeypatch):
    from app.services import llm

    async def fake_health(config):
        return True, 5.0, None

    async def fake_generate(config, prompt, system):
        return json.dumps({
            "milestones": [{
                "label": "House purchase", "target_month": 10,
                "down_payment": 80000, "recurring_payment": 2100,
                "recurring_months": 360, "asset_value": 400000,
                "debt_incurred": 320000,
            }],
            "parameters": {"safety_floor": 10000, "bogus_key": 1},
            "note": "Assumed a 30-year mortgage at 7%.",
        })

    monkeypatch.setattr(llm, "health", fake_health)
    monkeypatch.setattr(llm, "_generate", fake_generate)

    r = client.post(
        "/scenario/parse",
        json={"text": "What if I buy a $400k house in 10 months with 20% down?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["milestones"][0]["debt_incurred"] == 320000
    assert body["parameters"] == {"safety_floor": 10000}  # bogus key dropped
    assert "mortgage" in body["note"]


def test_scenario_parse_fails_clearly_when_offline(client, monkeypatch):
    from app.services import llm

    async def offline(config):
        return False, None, "no llm"

    monkeypatch.setattr(llm, "health", offline)
    r = client.post("/scenario/parse", json={"text": "buy a car next year"})
    assert r.status_code == 422
    assert "Connect a provider" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# Batched categorization through the import pipeline
# --------------------------------------------------------------------------- #
def test_import_uses_one_batch_call_per_chunk(client, monkeypatch):
    import time

    from app.services import llm

    calls = {"batch": 0, "single": 0}

    async def fake_health(config):
        return True, 5.0, None

    async def fake_batch(config, raws, cats):
        calls["batch"] += 1
        return [
            llm.CleanResult(clean_merchant=f"M{i}", category="Shopping")
            for i in range(len(raws))
        ]

    async def fake_single(config, raw, cats, retries=1):
        calls["single"] += 1
        return llm.CleanResult(clean_merchant="X", category="Shopping")

    monkeypatch.setattr(llm, "health", fake_health)
    monkeypatch.setattr(llm, "clean_merchants_batch", fake_batch)
    monkeypatch.setattr(llm, "clean_merchant", fake_single)

    rows = "\n".join(
        f"2026-06-{(i % 27) + 1:02d},VENDOR {i},-{10 + i}.00" for i in range(30)
    )
    csv_bytes = ("Date,Description,Amount\n" + rows).encode()
    r = client.post(
        "/import/csv", files={"files": ("big.csv", csv_bytes, "text/csv")}
    )
    job_id = r.json()["job_id"]
    for _ in range(300):
        status = client.get(f"/import/status/{job_id}").json()
        if status["state"] in ("done", "error"):
            break
        time.sleep(0.02)
    assert status["state"] == "done"
    assert status["imported"] == 30
    assert status["llm_cleaned"] == 30
    # 30 rows with chunk size 25 → exactly 2 batch calls, zero singles.
    assert calls["batch"] == 2
    assert calls["single"] == 0
