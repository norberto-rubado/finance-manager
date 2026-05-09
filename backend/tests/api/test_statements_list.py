"""Statements list/detail/review e2e。"""
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


def _import_alipay(client) -> int:
    p = _FIXTURES / "alipay_sample.csv"
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    with p.open("rb") as f:
        r = client.post("/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")})
    assert r.status_code == 200
    return r.json()["import_id"]


def test_list_statements_includes_imported(logged_in_client):
    import_id = _import_alipay(logged_in_client)
    resp = logged_in_client.get("/api/statements")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    ids = [s["id"] for s in body["items"]]
    assert import_id in ids


def test_list_statements_pagination(logged_in_client):
    _import_alipay(logged_in_client)
    resp = logged_in_client.get("/api/statements?limit=1&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) <= 1


def test_get_statement_detail(logged_in_client):
    import_id = _import_alipay(logged_in_client)
    resp = logged_in_client.get(f"/api/statements/{import_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == import_id
    assert body["source_type"] == "alipay_csv"


def test_get_statement_404(logged_in_client):
    resp = logged_in_client.get("/api/statements/9999999")
    assert resp.status_code == 404


def test_review_bundle_returns_unclassified_and_pending(logged_in_client):
    import_id = _import_alipay(logged_in_client)
    resp = logged_in_client.get(f"/api/statements/{import_id}/review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["statement"]["id"] == import_id
    # 未分类一般 > 0(用户的种子规则未必覆盖所有商户)
    assert isinstance(body["unclassified_transactions"], list)
    assert isinstance(body["pending_pairs"], list)


def test_review_404_when_statement_not_found(logged_in_client):
    resp = logged_in_client.get("/api/statements/9999999/review")
    assert resp.status_code == 404


def test_list_requires_login(client):
    resp = client.get("/api/statements")
    assert resp.status_code == 401
