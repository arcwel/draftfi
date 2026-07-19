"""Batch B: OFX/QFX/QIF parsing, column-mapping memory, multi-file import."""
from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.statement_parsers import parse_ofx, parse_qif, sniff_format

SAMPLES = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "imp.db"
    monkeypatch.setenv("DRAFTFI_DB_PATH", str(db_file))
    from app import config

    config.get_settings.cache_clear()
    main = importlib.import_module("app.main")

    from app.services import llm

    async def offline(cfg):
        return False, None, "offline"

    monkeypatch.setattr(llm, "health", offline)
    importlib.reload(main)
    monkeypatch.setattr(llm, "health", offline)
    with TestClient(main.create_app()) as c:
        yield c


def _wait(client, job_id):
    for _ in range(300):
        s = client.get(f"/import/status/{job_id}").json()
        if s["state"] in ("done", "error", "needs_mapping"):
            return s
        time.sleep(0.02)
    raise AssertionError("import did not finish")


def _upload(client, filenames, mapping=None):
    files = [
        ("files", (n, (SAMPLES / n).read_bytes(), "application/octet-stream"))
        for n in filenames
    ]
    data = {}
    if mapping is not None:
        data["mapping"] = json.dumps(mapping)
    r = client.post("/import/csv", files=files, data=data)
    assert r.status_code == 200, r.text
    return _wait(client, r.json()["job_id"])


# --------------------------------------------------------------------------- #
# B1 — OFX / QFX / QIF parsers
# --------------------------------------------------------------------------- #
def test_sniff_format():
    assert sniff_format("x.ofx", b"") == "ofx"
    assert sniff_format("x.qif", b"") == "qif"
    assert sniff_format("x.csv", b"") == "csv"
    assert sniff_format("noext", b"<OFX><STMTTRN>") == "ofx"
    assert sniff_format("noext", b"!Type:Bank\nD01/01/2026") == "qif"


def test_parse_ofx():
    report = parse_ofx((SAMPLES / "sample.ofx").read_bytes())
    assert len(report.rows) == 3
    payroll = next(r for r in report.rows if "PAYROLL" in r.raw_description)
    assert payroll.amount == 3200.0
    assert payroll.date == "2026-03-05"
    wf = next(r for r in report.rows if "WHOLEFDS" in r.raw_description)
    assert wf.amount == -88.40


def test_parse_qif():
    report = parse_qif((SAMPLES / "sample.qif").read_bytes())
    assert len(report.rows) == 3
    shell = next(r for r in report.rows if "SHELL" in r.raw_description)
    assert shell.amount == -52.10
    assert shell.date == "2026-03-05"
    dep = next(r for r in report.rows if "GLOBEX" in r.raw_description)
    assert dep.amount == 2500.0  # U-amount honored


def test_import_ofx_end_to_end(client):
    result = _upload(client, ["sample.ofx"])
    assert result["state"] == "done"
    assert result["imported"] == 3


def test_import_qif_end_to_end(client):
    result = _upload(client, ["sample.qif"])
    assert result["state"] == "done"
    assert result["imported"] == 3


# --------------------------------------------------------------------------- #
# B2 — column-mapping memory
# --------------------------------------------------------------------------- #
def test_unmappable_csv_requests_mapping(client):
    result = _upload(client, ["weird_bank.csv"])
    assert result["state"] == "needs_mapping"
    assert "Particulars" in result["headers"]
    assert result["sample_rows"]  # preview provided for the dialog
    assert result["signature"]


def test_manual_mapping_imports_and_is_remembered(client):
    # First attempt needs mapping.
    first = _upload(client, ["weird_bank.csv"])
    assert first["state"] == "needs_mapping"

    mapping = {
        "date": "Posted",
        "description": "Particulars",
        "debit": "Money Out",
        "credit": "Money In",
    }
    mapped = _upload(client, ["weird_bank.csv"], mapping=mapping)
    assert mapped["state"] == "done"
    assert mapped["imported"] == 2

    txs = client.get("/transactions").json()["items"]
    coffee = next(t for t in txs if "COFFEE" in t["raw_description"])
    assert coffee["amount"] == -4.50  # debit → negative
    salary = next(t for t in txs if "SALARY" in t["raw_description"])
    assert salary["amount"] == 3000.0  # credit → positive

    # Re-import the SAME bank layout with no mapping → remembered, no prompt.
    client.post("/reset")
    again = _upload(client, ["weird_bank.csv"])
    assert again["state"] == "done"
    assert again["imported"] == 2


# --------------------------------------------------------------------------- #
# B3 — multi-file import
# --------------------------------------------------------------------------- #
def test_multi_file_import_combines(client):
    result = _upload(client, ["chase_checking.csv", "sample.ofx", "sample.qif"])
    assert result["state"] == "done"
    # 6 (chase) + 3 (ofx) + 3 (qif) = 12
    assert result["imported"] == 12
    assert result["total"] == 12
    assert client.get("/transactions").json()["total"] == 12


def test_multi_file_skips_unmappable_without_blocking(client):
    # weird_bank has no saved mapping → skipped; chase imports fine.
    result = _upload(client, ["chase_checking.csv", "weird_bank.csv"])
    assert result["state"] == "done"
    assert result["imported"] == 6
    assert any("could not detect columns" in e for e in result["errors"])
