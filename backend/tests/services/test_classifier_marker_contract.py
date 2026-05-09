"""分类引擎对 marker 规则(category_id IS NULL)的契约 — slice A Rec #5。

本测试 freeze 行为契约,独立于 Task 14 的具体实现。Task 14 实现 classifier.py 时
必须让这些断言全部 pass。

契约:
- 普通规则(category_id is not None)命中:写 category_id + confidence + break
- marker 规则(category_id is None)命中:不写 category_id,不 break,加 hit_count,
  在 transaction.raw_payload['markers'] 累加 pattern
- 多条 marker 命中再命中真分类规则:markers 累加 + category 从真分类规则来
- 全部都 marker 命中:category_id 仍 None,markers 累加,confidence 留 None
"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Category, MerchantRule, Transaction, User


@pytest.fixture
def setup_user_and_categories(db):
    """构造一个 user + 一个最小分类树,返回 (user_id, categories_dict)。"""
    user = User(username="cls_test", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    # 餐饮(顶级)+ 餐饮/咖啡(子)
    cat_food = Category(user_id=user.id, name="餐饮", kind="expense", parent_id=None)
    db.add(cat_food)
    db.flush()
    cat_coffee = Category(user_id=user.id, name="咖啡", kind="expense", parent_id=cat_food.id)
    db.add(cat_coffee)
    db.flush()
    return user.id, {"food": cat_food.id, "coffee": cat_coffee.id}


@pytest.fixture
def setup_account(db, setup_user_and_categories):
    """给 user 建一个 wechat 账户,返回 account_id。"""
    user_id, _ = setup_user_and_categories
    acc = Account(user_id=user_id, name="微信支付", type="wechat", institution="微信支付", last4=None)
    db.add(acc)
    db.flush()
    return acc.id


def _make_tx(db, user_id, account_id, merchant_norm, amount=Decimal("12.50"), source="wechat"):
    """造一条未分类 transaction 用于测试。"""
    tx = Transaction(
        user_id=user_id,
        account_id=account_id,
        statement_import_id=None,
        tx_kind="expense",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        amount=amount,
        currency="CNY",
        amount_settled_cny=amount,
        merchant_raw=merchant_norm,
        merchant_normalized=merchant_norm,
        category_id=None,
        source=source,
        is_mirror=False,
        raw_payload={},
    )
    db.add(tx)
    db.flush()
    return tx


def _add_rule(db, user_id, pattern, match_kind, category_id, priority):
    r = MerchantRule(
        user_id=user_id,
        pattern=pattern,
        match_kind=match_kind,
        category_id=category_id,
        priority=priority,
    )
    db.add(r)
    db.flush()
    return r


# === 契约测试 ===

def test_normal_rule_hit_assigns_category_and_breaks(
    db, setup_user_and_categories, setup_account
):
    """普通规则命中:写 category_id + confidence=1.0 + hit_count++。"""
    from app.services.classifier import classify_transaction

    user_id, cats = setup_user_and_categories
    account_id = setup_account
    rule = _add_rule(db, user_id, "瑞幸咖啡", "fuzzy", cats["coffee"], priority=50)
    tx = _make_tx(db, user_id, account_id, "瑞幸咖啡")

    result = classify_transaction(db, tx)

    db.refresh(tx)
    db.refresh(rule)
    assert tx.category_id == cats["coffee"]
    assert tx.classification_confidence == 1.0
    assert rule.hit_count == 1
    assert result.matched_rule_id == rule.id


def test_marker_rule_hit_does_not_assign_but_logs_marker(
    db, setup_user_and_categories, setup_account
):
    """marker 规则(category_id IS NULL)命中:不写 category_id,在 raw_payload['markers'] 加 pattern,继续。"""
    from app.services.classifier import classify_transaction

    user_id, _ = setup_user_and_categories
    account_id = setup_account
    marker = _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    tx = _make_tx(db, user_id, account_id, "财付通-luckin")

    classify_transaction(db, tx)

    db.refresh(tx)
    db.refresh(marker)
    assert tx.category_id is None  # 没真分类
    assert tx.classification_confidence is None
    assert marker.hit_count == 1
    markers = (tx.raw_payload or {}).get("markers", [])
    assert "财付通-" in markers


def test_marker_then_real_rule_assigns_category_from_real_rule(
    db, setup_user_and_categories, setup_account
):
    """marker 规则命中后**继续**找真分类规则,真分类规则赋值 category。"""
    from app.services.classifier import classify_transaction

    user_id, cats = setup_user_and_categories
    account_id = setup_account
    marker = _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    real = _add_rule(db, user_id, "luckin", "contains", cats["coffee"], priority=50)
    tx = _make_tx(db, user_id, account_id, "财付通-luckin coffee")

    classify_transaction(db, tx)

    db.refresh(tx)
    db.refresh(marker)
    db.refresh(real)
    assert tx.category_id == cats["coffee"]  # 真分类生效
    assert tx.classification_confidence == 1.0
    assert marker.hit_count == 1
    assert real.hit_count == 1
    assert "财付通-" in (tx.raw_payload or {}).get("markers", [])


def test_only_markers_hit_keeps_unclassified(
    db, setup_user_and_categories, setup_account
):
    """全部命中的都是 marker → tx 仍未分类,但 markers 累加。"""
    from app.services.classifier import classify_transaction

    user_id, _ = setup_user_and_categories
    account_id = setup_account
    _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    _add_rule(db, user_id, "蚂蚁(", "contains", None, priority=20)
    tx = _make_tx(db, user_id, account_id, "财付通-蚂蚁(杭州)未知商家")

    classify_transaction(db, tx)

    db.refresh(tx)
    assert tx.category_id is None
    assert tx.classification_confidence is None
    markers = (tx.raw_payload or {}).get("markers", [])
    assert "财付通-" in markers
    assert "蚂蚁(" in markers


def test_no_rule_hit_keeps_unclassified_no_markers(
    db, setup_user_and_categories, setup_account
):
    """商户名不命中任何规则:category 留 None,markers 不存在或为空。"""
    from app.services.classifier import classify_transaction

    user_id, _ = setup_user_and_categories
    account_id = setup_account
    _add_rule(db, user_id, "瑞幸咖啡", "fuzzy", None, priority=50)  # 一个不命中的真规则
    tx = _make_tx(db, user_id, account_id, "完全陌生的商户名")

    classify_transaction(db, tx)

    db.refresh(tx)
    assert tx.category_id is None
    markers = (tx.raw_payload or {}).get("markers", []) if tx.raw_payload else []
    assert markers == []


def test_priority_order_respected_with_markers(
    db, setup_user_and_categories, setup_account
):
    """priority 小的先匹配。marker(priority 20)先 hit 不 break,真规则(priority 50)再 hit 才赋值。"""
    from app.services.classifier import classify_transaction

    user_id, cats = setup_user_and_categories
    account_id = setup_account
    # 故意倒序插入,验证 classifier 按 priority 排序而非插入顺序
    _add_rule(db, user_id, "luckin", "contains", cats["coffee"], priority=50)
    _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    tx = _make_tx(db, user_id, account_id, "财付通-luckin")

    classify_transaction(db, tx)

    db.refresh(tx)
    assert tx.category_id == cats["coffee"]
    assert "财付通-" in (tx.raw_payload or {}).get("markers", [])
