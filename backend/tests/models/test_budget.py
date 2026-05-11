"""Budget 模型 — 两个 partial unique index 验证。"""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Budget, User


@pytest.fixture
def u(db) -> User:
    user = User(username="u-budget", password_hash="x")
    db.add(user)
    db.flush()
    return user


def test_unique_total_budget_per_month(db, u):
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000")))
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("4000")))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_unique_category_budget_per_month(db, u):
    from app.models import Category
    cat = Category(user_id=u.id, name="c1", kind="expense")
    db.add(cat)
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat.id, amount=Decimal("500")))
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat.id, amount=Decimal("600")))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_different_months_are_independent(db, u):
    db.add(Budget(user_id=u.id, period_year=2026, period_month=4,
                  category_id=None, amount=Decimal("3000")))
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3500")))
    db.flush()  # 不应报错


def test_total_and_category_can_coexist(db, u):
    from app.models import Category
    cat = Category(user_id=u.id, name="c2", kind="expense")
    db.add(cat)
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000")))
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat.id, amount=Decimal("1500")))
    db.flush()  # 不应报错(NULL 和非 NULL 走的是不同的 partial index)
