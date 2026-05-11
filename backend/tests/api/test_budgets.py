"""Budgets API e2e。"""
from decimal import Decimal

from app.models import Budget, Category


def test_list_empty(logged_in_client):
    r = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_budgets(logged_in_client, db, admin_user):
    db.add(Budget(user_id=admin_user.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note="总"))
    db.flush()
    r = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["amount"] == "3000.00"
    assert items[0]["note"] == "总"
    assert items[0]["category_id"] is None


def test_list_requires_login(client):
    r = client.get("/api/budgets?year=2026&month=5")
    assert r.status_code == 401


def test_list_validates_query(logged_in_client):
    r = logged_in_client.get("/api/budgets?year=2026&month=13")
    assert r.status_code == 422


def test_put_creates_new(logged_in_client):
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "3000", "note": "总预算",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount"] == "3000.00"
    assert body["note"] == "总预算"
    assert body["id"] is not None


def test_put_updates_existing(logged_in_client):
    logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "3000", "note": "old",
    })
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "3500", "note": "new",
    })
    assert r.status_code == 200
    assert r.json()["amount"] == "3500.00"
    assert r.json()["note"] == "new"
    # 列表只有一条
    rl = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert len(rl.json()) == 1


def test_put_with_category(logged_in_client, db, admin_user):
    cat = Category(user_id=admin_user.id, name="餐饮-api", kind="expense")
    db.add(cat); db.flush()
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": cat.id, "amount": "1500", "note": None,
    })
    assert r.status_code == 200
    assert r.json()["category_id"] == cat.id


def test_put_validates_amount_negative(logged_in_client):
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "-100", "note": None,
    })
    assert r.status_code == 422
