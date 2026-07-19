"""Batch C: server-side search/sort/paging, splits, notes/tags, categories."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "ledger.db"
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(db_file))
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")
    importlib.reload(main)
    with TestClient(main.create_app()) as c:
        yield c


def _add(client, date, desc, amount, category=None, note=None, tags=None):
    body = {"date": date, "amount": amount, "raw_description": desc}
    if category:
        cats = client.get("/categories").json()
        body["category_id"] = next(c["id"] for c in cats if c["name"] == category)
    if note:
        body["note"] = note
    if tags:
        body["tags"] = tags
    r = client.post("/transactions", json=body)
    assert r.status_code == 201
    return r.json()


# --------------------------------------------------------------------------- #
# C1 — server-side search / sort / pagination
# --------------------------------------------------------------------------- #
def test_search_sort_and_paging(client):
    _add(client, "2026-01-05", "STARBUCKS #12", -6.5, "Dining")
    _add(client, "2026-02-10", "WHOLEFDS MKT", -80.0, "Groceries")
    _add(client, "2026-03-15", "STARBUCKS #99", -7.25, "Dining")

    # Text search matches descriptor.
    hits = client.get("/transactions", params={"q": "STARBUCKS"}).json()
    assert hits["total"] == 2

    # Search matches category name too.
    assert client.get("/transactions", params={"q": "Groceries"}).json()["total"] == 1

    # Sort by amount ascending: -80 first.
    page = client.get(
        "/transactions", params={"sort_by": "amount", "sort_dir": "asc"}
    ).json()
    assert page["items"][0]["amount"] == -80.0

    # Date-range filter.
    feb = client.get(
        "/transactions", params={"date_from": "2026-02-01", "date_to": "2026-02-28"}
    ).json()
    assert feb["total"] == 1

    # Pagination: page size 2 → totals stay global.
    p1 = client.get("/transactions", params={"limit": 2, "offset": 0}).json()
    p2 = client.get("/transactions", params={"limit": 2, "offset": 2}).json()
    assert p1["total"] == 3 and len(p1["items"]) == 2 and len(p2["items"]) == 1


def test_search_matches_notes_and_tags(client):
    _add(client, "2026-01-05", "AMAZON", -30, note="birthday gift for Sam",
         tags=["gift", "family"])
    assert client.get("/transactions", params={"q": "birthday"}).json()["total"] == 1
    assert client.get("/transactions", params={"q": "family"}).json()["total"] == 1


# --------------------------------------------------------------------------- #
# C2 — split transactions
# --------------------------------------------------------------------------- #
def test_split_and_unsplit(client):
    tx = _add(client, "2026-01-10", "COSTCO WHOLESALE", -100.0)
    cats = client.get("/categories").json()
    groceries = next(c["id"] for c in cats if c["name"] == "Groceries")
    shopping = next(c["id"] for c in cats if c["name"] == "Shopping")

    # Wrong sum rejected.
    bad = client.post(
        f"/transactions/{tx['id']}/split",
        json={"splits": [{"amount": -50, "category_id": groceries},
                         {"amount": -20, "category_id": shopping}]},
    )
    assert bad.status_code == 400

    parts = client.post(
        f"/transactions/{tx['id']}/split",
        json={"splits": [{"amount": -70, "category_id": groceries},
                         {"amount": -30, "category_id": shopping}]},
    )
    assert parts.status_code == 200
    kids = parts.json()
    assert len(kids) == 2
    assert all(k["parent_tx_id"] == tx["id"] for k in kids)
    assert all(k["resolution"] == "split" for k in kids)

    # Budget counts the parts, not the parent (no double counting).
    budget = client.post("/budget", json={"parameters": {}, "milestones": []}).json()
    total_expense = budget["total_monthly_expense"]
    assert abs(total_expense - 100.0) < 0.01
    by_name = {c["name"]: c for c in budget["categories"]}
    assert by_name["Groceries"]["monthly_amount"] == 70.0
    assert by_name["Shopping"]["monthly_amount"] == 30.0

    # Double-split is rejected; unsplit restores.
    assert client.post(
        f"/transactions/{tx['id']}/split",
        json={"splits": [{"amount": -50}, {"amount": -50}]},
    ).status_code == 400
    restored = client.post(f"/transactions/{tx['id']}/unsplit")
    assert restored.status_code == 200
    assert restored.json()["is_split_parent"] is False
    assert client.get("/transactions").json()["total"] == 1


def test_deleting_split_parent_removes_children(client):
    tx = _add(client, "2026-01-10", "TARGET", -60.0)
    client.post(
        f"/transactions/{tx['id']}/split",
        json={"splits": [{"amount": -40}, {"amount": -20}]},
    )
    assert client.get("/transactions").json()["total"] == 3  # parent + 2 kids
    client.delete(f"/transactions/{tx['id']}")
    assert client.get("/transactions").json()["total"] == 0


# --------------------------------------------------------------------------- #
# C3 — notes & tags
# --------------------------------------------------------------------------- #
def test_note_and_tags_roundtrip(client):
    tx = _add(client, "2026-01-05", "DELTA AIR", -400)
    patched = client.patch(
        f"/transactions/{tx['id']}",
        json={"note": "flight to see family", "tags": ["travel", "reimbursable"]},
    ).json()
    assert patched["note"] == "flight to see family"
    assert patched["tags"] == ["travel", "reimbursable"]

    # Clearing tags works.
    cleared = client.patch(f"/transactions/{tx['id']}", json={"tags": []}).json()
    assert cleared["tags"] == []


# --------------------------------------------------------------------------- #
# C4 — category management
# --------------------------------------------------------------------------- #
def test_category_create_rename_recolor(client):
    created = client.post(
        "/categories", json={"name": "Pets", "color": "#AB47BC"}
    )
    assert created.status_code == 201
    cat = created.json()
    # Duplicate name rejected.
    assert client.post("/categories", json={"name": "Pets"}).status_code == 409

    renamed = client.patch(
        f"/categories/{cat['id']}", json={"name": "Pet Care", "color": "#123456"}
    ).json()
    assert renamed["name"] == "Pet Care"
    assert renamed["color"] == "#123456"


def test_category_merge_repoints_transactions_and_cache(client):
    coffee = client.post("/categories", json={"name": "Coffee"}).json()
    tx = _add(client, "2026-01-05", "BLUE BOTTLE", -6.0)
    client.patch(
        f"/transactions/{tx['id']}/category", json={"category_id": coffee["id"]}
    )  # also writes a cache rule for BLUE BOTTLE

    cats = client.get("/categories").json()
    dining = next(c for c in cats if c["name"] == "Dining")
    merged = client.post(
        f"/categories/{coffee['id']}/merge", json={"target_id": dining["id"]}
    )
    assert merged.status_code == 200
    # Category gone; transaction re-pointed.
    names = {c["name"] for c in client.get("/categories").json()}
    assert "Coffee" not in names
    moved = client.get("/transactions").json()["items"][0]
    assert moved["category_name"] == "Dining"


def test_delete_category_falls_back_to_uncategorized(client):
    snacks = client.post("/categories", json={"name": "Snacks"}).json()
    _add(client, "2026-01-06", "VENDING", -2.0, category="Snacks")
    assert client.delete(f"/categories/{snacks['id']}").status_code == 204
    tx = client.get("/transactions").json()["items"][0]
    assert tx["category_name"] == "Uncategorized"


def test_uncategorized_is_protected(client):
    cats = client.get("/categories").json()
    uncat = next(c for c in cats if c["name"] == "Uncategorized")
    other = next(c for c in cats if c["name"] == "Dining")
    assert client.delete(f"/categories/{uncat['id']}").status_code == 403
    assert client.post(
        f"/categories/{uncat['id']}/merge", json={"target_id": other["id"]}
    ).status_code == 403
