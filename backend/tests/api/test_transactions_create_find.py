"""POST /api/transactions/manual + GET /merchants + GET /pending-classifications 测试。

slice E Task 1/2/3 端点共用此文件 — 三组测试用 # === Section ===  注释分隔。
"""
from __future__ import annotations

import pytest

from app.models import Account, Category, MerchantRule

# === Section: POST /api/transactions/manual (Task 1) ===

@pytest.fixture
def alipay_account(db, admin_user) -> Account:
    acc = Account(
        user_id=admin_user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None, currency="CNY",
    )
    db.add(acc); db.flush()
    return acc


@pytest.fixture
def cafe_category(db, admin_user) -> Category:
    cat = Category(
        user_id=admin_user.id, name="餐饮/咖啡",
        kind="expense", sort_order=10,
    )
    db.add(cat); db.flush()
    return cat


def test_create_manual_transaction_basic(logged_in_client, alipay_account, cafe_category, db, admin_user):
    """最简 happy path — time + amount + merchant + account_id + category_id 显式给。"""
    body = {
        "tx_time": "2026-05-10T12:30:00",
        "amount": "23.50",
        "currency": "CNY",
        "merchant": "瑞幸咖啡  五道口店",
        "account_id": alipay_account.id,
        "category_id": cafe_category.id,
        "tx_kind": "expense",
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["amount"] == "23.50"
    assert data["currency"] == "CNY"
    assert data["account_id"] == alipay_account.id
    assert data["category_id"] == cafe_category.id
    assert data["source"] == "manual"
    assert data["tx_kind"] == "expense"
    # merchant_normalized 应已 normalize(去多余空格、保留主名)
    assert "瑞幸咖啡" in data["merchant_normalized"]
    # is_mirror 默认 False
    assert data["is_mirror"] is False


def test_create_manual_transaction_classifier_hits_rule(
    logged_in_client, alipay_account, cafe_category, db, admin_user,
):
    """category_id 不给,但商家规则命中 → 自动归类。

    用独特 pattern + priority=5(早于 seed 优先级 10 的还款规则)避开 seed_merchant_rules
    在 dev 库残留可能命中的同类种子(如 "瑞幸咖啡" priority 50)。
    """
    rule = MerchantRule(
        user_id=admin_user.id, pattern="测试虚构商户XYZ",
        match_kind="contains", category_id=cafe_category.id, priority=5,
    )
    db.add(rule); db.flush()

    body = {
        "tx_time": "2026-05-10T08:00:00",
        "amount": "18.00",
        "merchant": "测试虚构商户XYZ 五道口店",
        "account_id": alipay_account.id,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # 规则命中 → category_id 被填,confidence=1.0
    assert data["category_id"] == cafe_category.id
    assert data["classification_confidence"] == 1.0


def test_create_manual_transaction_no_rule_match_uncategorized(
    logged_in_client, alipay_account, db, admin_user,
):
    """没规则命中 + 不显式给 category → 进未分类(category_id=None)。"""
    body = {
        "tx_time": "2026-05-10T18:00:00",
        "amount": "100.00",
        "merchant": "某不知名小馆",
        "account_id": alipay_account.id,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 201
    data = resp.json()
    assert data["category_id"] is None
    assert data["classification_confidence"] is None


def test_create_manual_transaction_invalid_account_404(logged_in_client):
    body = {
        "tx_time": "2026-05-10T12:00:00",
        "amount": "10.00",
        "merchant": "x",
        "account_id": 999999,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 404
    assert "account" in resp.json()["detail"].lower()


def test_create_manual_transaction_invalid_category_404(
    logged_in_client, alipay_account,
):
    body = {
        "tx_time": "2026-05-10T12:00:00",
        "amount": "10.00",
        "merchant": "x",
        "account_id": alipay_account.id,
        "category_id": 999999,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 404
    assert "category" in resp.json()["detail"].lower()


def test_create_manual_transaction_negative_amount_422(logged_in_client, alipay_account):
    body = {
        "tx_time": "2026-05-10T12:00:00",
        "amount": "-10.00",
        "merchant": "x",
        "account_id": alipay_account.id,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 422  # Pydantic 拒绝负数(Field gt=0)
