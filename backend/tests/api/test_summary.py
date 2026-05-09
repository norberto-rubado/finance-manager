"""Summary API e2e。"""
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


@pytest.fixture
def imported_alipay(logged_in_client):
    p = _FIXTURES / "alipay_sample.csv"
    if not p.exists():
        pytest.skip("fixture missing")
    with p.open("rb") as f:
        r = logged_in_client.post("/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")})
    assert r.status_code == 200


def test_summary_default_month_category(logged_in_client, imported_alipay):
    resp = logged_in_client.get("/api/summary")  # 默认 period=month, group_by=category
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "month"
    assert body["group_by"] == "category"
    # 真实样本可能在 3 月,与"本月"不一定重合;改用显式 date 范围测一次:
    resp2 = logged_in_client.get(
        "/api/summary?date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00")
    body2 = resp2.json()
    assert float(body2["total_expense"]) >= 0


def test_summary_group_by_merchant(logged_in_client, imported_alipay):
    resp = logged_in_client.get(
        "/api/summary?group_by=merchant"
        "&date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00")
    assert resp.status_code == 200
    body = resp.json()
    assert body["group_by"] == "merchant"
    assert isinstance(body["breakdown"], list)


def test_summary_group_by_account(logged_in_client, imported_alipay):
    resp = logged_in_client.get(
        "/api/summary?group_by=account"
        "&date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00")
    assert resp.status_code == 200


def test_summary_invalid_group_by_returns_422(logged_in_client):
    resp = logged_in_client.get("/api/summary?group_by=invalid")
    assert resp.status_code == 422


def test_summary_requires_login(client):
    resp = client.get("/api/summary")
    assert resp.status_code == 401
