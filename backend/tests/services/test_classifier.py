"""classifier 实现测试(非契约,实现细节)。"""
import re
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Category, MerchantRule, Transaction, User
from app.services.classifier import classify_batch, classify_transaction, _match_rule


@pytest.fixture
def setup(db):
    user = User(username="cl", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    cat = Category(user_id=user.id, name="餐饮", kind="expense", parent_id=None)
    db.add(cat); db.flush()
    coffee = Category(user_id=user.id, name="咖啡", kind="expense", parent_id=cat.id)
    db.add(coffee); db.flush()
    acc = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", last4=None)
    db.add(acc); db.flush()
    return user, acc, {"food": cat.id, "coffee": coffee.id}


def _mk_tx(db, user_id, account_id, merchant, **kw):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=datetime(2026, 3, 1, 12, 0),
        amount=Decimal("10.00"), currency="CNY", amount_settled_cny=Decimal("10.00"),
        merchant_raw=merchant, merchant_normalized=merchant,
        category_id=None, source=kw.get("source", "alipay"),
        is_mirror=False, raw_payload=kw.get("raw_payload") or {},
    )
    db.add(tx); db.flush()
    return tx


def _add_rule(db, user_id, pattern, match_kind, category_id=None, priority=100):
    r = MerchantRule(user_id=user_id, pattern=pattern, match_kind=match_kind,
        category_id=category_id, priority=priority)
    db.add(r); db.flush()
    return r


def test_match_rule_exact():
    assert _match_rule("瑞幸咖啡", "瑞幸咖啡", "exact") is True
    assert _match_rule("瑞幸咖啡 北京", "瑞幸咖啡", "exact") is False


def test_match_rule_contains_case_insensitive():
    assert _match_rule("Luckin Coffee", "luckin", "contains") is True
    assert _match_rule("LUCKIN COFFEE", "luckin", "contains") is True
    assert _match_rule("星巴克", "luckin", "contains") is False


def test_match_rule_regex():
    assert _match_rule("银联入账7432", r"银联入账.*\d{4}", "regex") is True
    assert _match_rule("普通商户", r"银联入账.*\d{4}", "regex") is False


def test_match_rule_fuzzy_ratio_threshold():
    """fuzzy 默认 ratio>=80。"""
    # rapidfuzz.WRatio("瑞幸咖啡", "瑞幸 咖啡") 应该很高
    assert _match_rule("瑞幸 咖啡", "瑞幸咖啡", "fuzzy") is True
    # 完全不相关
    assert _match_rule("电信费", "瑞幸咖啡", "fuzzy") is False


def test_classify_batch_assigns_and_counts(db, setup):
    user, acc, cats = setup
    _add_rule(db, user.id, "瑞幸咖啡", "fuzzy", cats["coffee"], priority=50)
    _add_rule(db, user.id, "财付通-", "contains", None, priority=20)
    txs = [
        _mk_tx(db, user.id, acc.id, "瑞幸咖啡 北京"),
        _mk_tx(db, user.id, acc.id, "财付通-美团"),
        _mk_tx(db, user.id, acc.id, "陌生商户"),
    ]
    classified, marker_only = classify_batch(
        db, user_id=user.id, tx_ids=[t.id for t in txs])
    db.flush()
    assert classified == 1
    assert marker_only == 1   # 财付通-美团 命中 marker 但无真分类规则


def test_classify_does_nothing_for_already_classified(db, setup):
    """已有 category_id 的 tx 不应被重新分类(避免覆盖用户手工改类)。"""
    user, acc, cats = setup
    _add_rule(db, user.id, "瑞幸咖啡", "fuzzy", cats["coffee"], priority=50)
    tx = _mk_tx(db, user.id, acc.id, "瑞幸咖啡 北京")
    tx.category_id = cats["food"]  # 用户手工选了"餐饮"父分类
    tx.classification_confidence = 0.5  # 之前 Agent 模糊归类
    db.flush()
    classify_transaction(db, tx)
    db.refresh(tx)
    assert tx.category_id == cats["food"]  # 不动
    assert tx.classification_confidence == 0.5
