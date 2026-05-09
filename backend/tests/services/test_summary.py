"""compute_summary 单元测试。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Category, Transaction, User
from app.services.summary import compute_summary


@pytest.fixture
def populated(db):
    user = User(username="su", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    cat_food = Category(user_id=user.id, name="餐饮", kind="expense", parent_id=None)
    cat_traffic = Category(user_id=user.id, name="交通", kind="expense", parent_id=None)
    db.add_all([cat_food, cat_traffic]); db.flush()
    acc1 = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add(acc1); db.flush()

    txs = [
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 1, 12),
            amount=Decimal("10"), currency="CNY", amount_settled_cny=Decimal("10"),
            merchant_raw="瑞幸", merchant_normalized="瑞幸",
            category_id=cat_food.id, source="alipay", is_mirror=False,
            source_unique_key="alipay:t1"),
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 2, 12),
            amount=Decimal("20"), currency="CNY", amount_settled_cny=Decimal("20"),
            merchant_raw="星巴克", merchant_normalized="星巴克",
            category_id=cat_food.id, source="alipay", is_mirror=False,
            source_unique_key="alipay:t2"),
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 3, 12),
            amount=Decimal("30"), currency="CNY", amount_settled_cny=Decimal("30"),
            merchant_raw="地铁", merchant_normalized="地铁",
            category_id=cat_traffic.id, source="alipay", is_mirror=False,
            source_unique_key="alipay:t3"),
        # is_mirror=True 应被过滤
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 4, 12),
            amount=Decimal("999"), currency="CNY", amount_settled_cny=Decimal("999"),
            merchant_raw="MIRROR", merchant_normalized="MIRROR",
            category_id=cat_food.id, source="bank", is_mirror=True,
            source_unique_key="bank:m1"),
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="income", tx_time=datetime(2026, 3, 5, 12),
            amount=Decimal("100"), currency="CNY", amount_settled_cny=Decimal("100"),
            merchant_raw="工资", merchant_normalized="工资",
            category_id=None, source="bank", is_mirror=False,
            source_unique_key="bank:i1"),
    ]
    db.add_all(txs); db.flush()
    return user, {"food": cat_food.id, "traffic": cat_traffic.id, "acc": acc1.id}


def test_summary_total_excludes_mirror(populated, db):
    user, _ = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="category")
    assert s["total_expense"] == Decimal("60")  # 10+20+30,排除 mirror 999
    assert s["total_income"] == Decimal("100")


def test_summary_group_by_category(populated, db):
    user, ids = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="category")
    bd = {item["group_id"]: item for item in s["breakdown"]}
    assert bd[ids["food"]]["amount"] == Decimal("30")  # 10+20
    assert bd[ids["food"]]["count"] == 2
    assert bd[ids["traffic"]]["amount"] == Decimal("30")
    assert bd[ids["traffic"]]["count"] == 1


def test_summary_group_by_merchant(populated, db):
    user, _ = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="merchant")
    keys = {item["group_key"] for item in s["breakdown"]}
    assert {"瑞幸", "星巴克", "地铁"}.issubset(keys)


def test_summary_group_by_account(populated, db):
    user, ids = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="account")
    bd = {item["group_id"]: item for item in s["breakdown"]}
    assert bd[ids["acc"]]["count"] == 3  # 3 条 expense,排除 mirror


def test_summary_date_filter(populated, db):
    user, _ = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 2), date_to=datetime(2026, 3, 3, 23, 59),
        group_by="category")
    assert s["total_expense"] == Decimal("50")  # 20+30
