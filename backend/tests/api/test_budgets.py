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
