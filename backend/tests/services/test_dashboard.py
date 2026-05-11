"""Dashboard service 测试 — 三月均值 / 节奏 / overspending。"""
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models import Account, Budget, Category, Transaction, User
from app.services.dashboard import (
    _compute_pace,
    _shift_month,
    compute_dashboard_snapshot,
    compute_three_month_avg,
)


@pytest.fixture
def u(db) -> User:
    user = User(username="u-dash", password_hash="x")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def acct(db, u) -> Account:
    a = Account(user_id=u.id, name="a-dash", type="bank_debit")
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def cat_food(db, u) -> Category:
    c = Category(user_id=u.id, name="餐饮", kind="expense")
    db.add(c)
    db.flush()
    return c


def _add_tx(db, u, acct, cat, amount: str, when: datetime, kind: str = "expense") -> None:
    db.add(Transaction(
        user_id=u.id, account_id=acct.id, tx_kind=kind, tx_time=when,
        amount=Decimal(amount), amount_settled_cny=Decimal(amount),
        currency="CNY", source="manual", category_id=cat.id if cat else None,
    ))
    db.flush()


def test_shift_month():
    assert _shift_month(2026, 1, -1) == (2025, 12)
    assert _shift_month(2026, 12, 1) == (2027, 1)
    assert _shift_month(2026, 5, -3) == (2026, 2)


def test_compute_pace_current_month_no_budget():
    p = _compute_pace(is_current_month=True, day_of_month=15,
                      total_days=30, spent=Decimal("500"), budget=None)
    assert p["expected_ratio"] == 0.5
    assert p["actual_ratio"] is None
    assert p["delta_pct"] is None


def test_compute_pace_current_month_with_budget():
    p = _compute_pace(is_current_month=True, day_of_month=15,
                      total_days=30, spent=Decimal("750"),
                      budget=Decimal("1000"))
    assert p["expected_ratio"] == 0.5
    assert p["actual_ratio"] == 0.75
    # delta = (0.75 - 0.5) / 0.5 * 100 = 50
    assert p["delta_pct"] == 50.0


def test_compute_pace_past_month():
    p = _compute_pace(is_current_month=False, day_of_month=30,
                      total_days=30, spent=Decimal("1000"),
                      budget=Decimal("1000"))
    assert p["expected_ratio"] == 1.0
    assert p["actual_ratio"] == 1.0
    assert p["delta_pct"] == 0.0


def test_three_month_avg_no_data(db, u):
    assert compute_three_month_avg(
        db, user_id=u.id, query_year=2026, query_month=5,
    ) == {}


def test_three_month_avg_partial_data(db, u, acct, cat_food):
    # 4 月有数据,3 月、2 月没
    _add_tx(db, u, acct, cat_food, "100", datetime(2026, 4, 15))
    _add_tx(db, u, acct, cat_food, "200", datetime(2026, 4, 20))
    avg = compute_three_month_avg(
        db, user_id=u.id, query_year=2026, query_month=5,
    )
    # 总 300,只有 1 个月有数据,分母 1 → avg = 300
    assert avg[cat_food.id] == Decimal("300.00")


def test_three_month_avg_full_data(db, u, acct, cat_food):
    _add_tx(db, u, acct, cat_food, "300", datetime(2026, 4, 15))
    _add_tx(db, u, acct, cat_food, "600", datetime(2026, 3, 15))
    _add_tx(db, u, acct, cat_food, "300", datetime(2026, 2, 15))
    avg = compute_three_month_avg(
        db, user_id=u.id, query_year=2026, query_month=5,
    )
    # 总 1200 / 3 = 400
    assert avg[cat_food.id] == Decimal("400.00")


def test_snapshot_no_budget_no_data(db, u):
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    assert snap["total"]["budget"] is None
    assert snap["total"]["spent"] == Decimal("0")
    assert snap["pace"]["actual_ratio"] is None
    assert snap["period"]["is_current_month"] is True
    assert snap["period"]["day_of_month"] == 11
    assert snap["pending"]["uncategorized_count"] == 0
    assert snap["pending"]["overspending_count"] == 0


def test_snapshot_past_month_hides_pending(db, u):
    """非本月查询:pending 全 0,is_current_month=False。"""
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=4,
        client_date=date(2026, 5, 11),
    )
    assert snap["period"]["is_current_month"] is False
    assert snap["pace"]["expected_ratio"] == 1.0
    assert snap["pending"]["uncategorized_count"] == 0
    assert snap["pending"]["dedup_pending_count"] == 0


def test_snapshot_overspending(db, u, acct, cat_food):
    """本月 1500 支出,预算 1000 → is_overspending=True。"""
    _add_tx(db, u, acct, cat_food, "1500", datetime(2026, 5, 10))
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat_food.id, amount=Decimal("1000")))
    db.flush()
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    food_row = next(c for c in snap["categories"] if c["category_id"] == cat_food.id)
    assert food_row["is_overspending"] is True
    assert snap["pending"]["overspending_count"] == 1


def test_snapshot_month_trend_6_months(db, u):
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    trend = snap["monthly_trend"]
    assert len(trend) == 6
    # 升序:第一项是 2025 年 12 月,最后一项是 2026 年 5 月
    assert trend[0]["year"] == 2025 and trend[0]["month"] == 12
    assert trend[-1]["year"] == 2026 and trend[-1]["month"] == 5


def test_snapshot_prev_month_spent(db, u, acct, cat_food):
    _add_tx(db, u, acct, cat_food, "888", datetime(2026, 4, 15))
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    assert snap["total"]["prev_month_spent"] == Decimal("888.00")
