"""Dashboard API e2e — spec § 4.5 / overview 切片 B DoD 5 场景。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Account, Budget, Category, Transaction


@pytest.fixture
def cat_food(db, admin_user) -> Category:
    c = Category(user_id=admin_user.id, name="餐饮-dash", kind="expense")
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def acct(db, admin_user) -> Account:
    a = Account(user_id=admin_user.id, name="a-dash", type="bank_debit")
    db.add(a)
    db.flush()
    return a


def _q(year: int, month: int, client_date: str) -> str:
    return f"/api/dashboard/snapshot?year={year}&month={month}&client_date={client_date}"


def test_snapshot_requires_login(client):
    r = client.get(_q(2026, 5, "2026-05-11"))
    assert r.status_code == 401


def test_snapshot_no_budget(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"]["budget"] is None
    assert body["pace"]["actual_ratio"] is None
    assert body["pending"]["overspending_count"] == 0


def test_snapshot_month_start_day_1(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-01"))
    body = r.json()
    assert body["period"]["day_of_month"] == 1
    # 5 月共 31 天
    assert body["period"]["total_days"] == 31
    assert abs(body["pace"]["expected_ratio"] - 1/31) < 0.001


def test_snapshot_prev_month_no_data(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    body = r.json()
    assert body["total"]["prev_month_spent"] == "0.00"


def test_snapshot_overspending(logged_in_client, db, admin_user, acct, cat_food):
    db.add(Transaction(
        user_id=admin_user.id, account_id=acct.id, tx_kind="expense",
        tx_time=datetime(2026, 5, 10),
        amount=Decimal("1500"), amount_settled_cny=Decimal("1500"),
        currency="CNY", source="manual", category_id=cat_food.id,
    ))
    db.add(Budget(user_id=admin_user.id, period_year=2026, period_month=5,
                  category_id=cat_food.id, amount=Decimal("1000")))
    db.flush()
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    body = r.json()
    assert body["pending"]["overspending_count"] == 1
    food = next(c for c in body["categories"] if c["category_id"] == cat_food.id)
    assert food["is_overspending"] is True


def test_snapshot_non_current_month(logged_in_client):
    r = logged_in_client.get(_q(2026, 4, "2026-05-11"))
    body = r.json()
    assert body["period"]["is_current_month"] is False
    assert body["pace"]["expected_ratio"] == 1.0
    assert body["pending"]["uncategorized_count"] == 0
    assert body["pending"]["dedup_pending_count"] == 0


def test_snapshot_invalid_query(logged_in_client):
    r = logged_in_client.get("/api/dashboard/snapshot?year=2026&month=5")
    assert r.status_code == 422   # 缺 client_date

    r = logged_in_client.get(_q(2026, 13, "2026-05-11"))
    assert r.status_code == 422   # month > 12


def test_snapshot_trend_has_6_months(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    trend = r.json()["monthly_trend"]
    assert len(trend) == 6
    # 升序
    assert trend[0]["month"] == 12 and trend[0]["year"] == 2025
    assert trend[-1]["month"] == 5 and trend[-1]["year"] == 2026
