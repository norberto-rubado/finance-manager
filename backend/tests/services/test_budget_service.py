"""Budget service 单元测试 — upsert + copy 边界。"""
from decimal import Decimal

import pytest

from app.models import Category, User
from app.services.budget import copy_budgets_from, list_budgets, upsert_budget


@pytest.fixture
def admin(db) -> User:
    user = User(username="admin-svc", password_hash="x")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def cat_food(db, admin) -> Category:
    cat = Category(user_id=admin.id, name="餐饮-test", kind="expense")
    db.add(cat)
    db.flush()
    return cat


def test_upsert_creates_new(db, admin):
    b = upsert_budget(
        db, user_id=admin.id, period_year=2026, period_month=5,
        category_id=None, amount=Decimal("3000"), note="总预算",
    )
    assert b.id is not None
    assert b.amount == Decimal("3000.00")


def test_upsert_updates_existing(db, admin):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note="old")
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3500"), note="new")
    rows = list_budgets(db, user_id=admin.id, period_year=2026, period_month=5)
    assert len(rows) == 1
    assert rows[0].amount == Decimal("3500.00")
    assert rows[0].note == "new"


def test_upsert_total_and_category_independent(db, admin, cat_food):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note=None)
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=cat_food.id, amount=Decimal("1500"), note=None)
    rows = list_budgets(db, user_id=admin.id, period_year=2026, period_month=5)
    assert len(rows) == 2


def test_copy_from_happy(db, admin, cat_food):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=4,
                  category_id=None, amount=Decimal("3000"), note=None)
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=4,
                  category_id=cat_food.id, amount=Decimal("1500"), note="餐饮")
    created, conflict = copy_budgets_from(
        db, user_id=admin.id, from_year=2026, from_month=4,
        to_year=2026, to_month=5,
    )
    assert conflict is False
    assert len(created) == 2
    rows_may = list_budgets(db, user_id=admin.id, period_year=2026, period_month=5)
    assert len(rows_may) == 2


def test_copy_from_empty_source(db, admin):
    """上月没数据 → 返回空 list,不报错。"""
    created, conflict = copy_budgets_from(
        db, user_id=admin.id, from_year=2026, from_month=3,
        to_year=2026, to_month=5,
    )
    assert conflict is False
    assert created == []


def test_copy_from_target_already_has_data(db, admin, cat_food):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note=None)
    created, conflict = copy_budgets_from(
        db, user_id=admin.id, from_year=2026, from_month=4,
        to_year=2026, to_month=5,
    )
    assert conflict is True
    assert created == []
