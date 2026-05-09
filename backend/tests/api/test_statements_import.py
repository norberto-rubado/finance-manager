"""POST /api/statements/import e2e。"""
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


def _open(name: str):
    p = _FIXTURES / name
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return p


def test_import_alipay_csv_returns_200(logged_in_client):
    p = _open("alipay_sample.csv")
    with p.open("rb") as f:
        resp = logged_in_client.post(
            "/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_type"] == "alipay_csv"
    assert body["imported_count"] >= 1


def test_import_unsupported_returns_400(logged_in_client):
    resp = logged_in_client.post(
        "/api/statements/import",
        files={"file": ("x.txt", b"random data", "text/plain")},
    )
    assert resp.status_code == 400
    assert "unsupported" in resp.json()["detail"].lower()


def test_import_duplicate_returns_409(logged_in_client):
    p = _open("alipay_sample.csv")
    with p.open("rb") as f:
        bytes_ = f.read()
    r1 = logged_in_client.post("/api/statements/import",
        files={"file": ("alipay_sample.csv", bytes_, "text/csv")})
    assert r1.status_code == 200
    r2 = logged_in_client.post("/api/statements/import",
        files={"file": ("alipay_sample_renamed.csv", bytes_, "text/csv")})
    assert r2.status_code == 409


def test_import_requires_login(client):
    """无 cookie 应 401。"""
    resp = client.post("/api/statements/import",
        files={"file": ("x.csv", b"data", "text/csv")})
    assert resp.status_code == 401


def test_import_empty_file_400(logged_in_client):
    resp = logged_in_client.post("/api/statements/import",
        files={"file": ("x.csv", b"", "text/csv")})
    assert resp.status_code == 400
