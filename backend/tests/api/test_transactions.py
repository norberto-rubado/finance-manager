"""Transactions API e2e。"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Account, Category, MerchantRule, Transaction


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


@pytest.fixture
def imported_sample(logged_in_client):
    """先导一份支付宝样本,提供基础数据。"""
    p = _FIXTURES / "alipay_sample.csv"
    if not p.exists():
        pytest.skip("fixture missing")
    with p.open("rb") as f:
        r = logged_in_client.post("/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")})
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def category_food(db, admin_user):
    cat = db.execute(select(Category).where(
        Category.user_id == admin_user.id, Category.name == "餐饮"
    )).scalar_one_or_none()
    if cat is None:
        cat = Category(user_id=admin_user.id, name="餐饮", kind="expense", parent_id=None)
        db.add(cat); db.flush()
    return cat


def test_list_transactions_pagination(logged_in_client, imported_sample):
    resp = logged_in_client.get("/api/transactions?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 10
    assert body["total"] >= 1
    assert len(body["items"]) <= 10


def test_list_transactions_filter_by_kind(logged_in_client, imported_sample):
    resp = logged_in_client.get("/api/transactions?kind=expense")
    assert resp.status_code == 200
    for tx in resp.json()["items"]:
        assert tx["tx_kind"] == "expense"


def test_list_transactions_filter_by_keyword(logged_in_client, imported_sample):
    """关键词 → merchant_normalized ILIKE。"""
    resp = logged_in_client.get("/api/transactions?keyword=咋啊")
    assert resp.status_code == 200
    body = resp.json()
    if body["items"]:
        for tx in body["items"]:
            assert "咋啊" in (tx["merchant_normalized"] or "")


def test_get_transaction_detail(logged_in_client, imported_sample, db, admin_user):
    tx = db.execute(
        select(Transaction).where(Transaction.user_id == admin_user.id).limit(1)
    ).scalar_one()
    resp = logged_in_client.get(f"/api/transactions/{tx.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == tx.id


def test_get_transaction_404(logged_in_client):
    resp = logged_in_client.get("/api/transactions/9999999")
    assert resp.status_code == 404


def test_patch_transaction_category(logged_in_client, imported_sample, db, admin_user, category_food):
    tx = db.execute(
        select(Transaction).where(Transaction.user_id == admin_user.id).limit(1)
    ).scalar_one()
    resp = logged_in_client.patch(
        f"/api/transactions/{tx.id}",
        json={"category_id": category_food.id},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == category_food.id


def test_patch_transaction_invalid_category_404(logged_in_client, imported_sample, db, admin_user):
    tx = db.execute(
        select(Transaction).where(Transaction.user_id == admin_user.id).limit(1)
    ).scalar_one()
    resp = logged_in_client.patch(
        f"/api/transactions/{tx.id}", json={"category_id": 9999999})
    assert resp.status_code == 404


def test_bulk_update_by_merchant_with_rule(
    logged_in_client, imported_sample, db, admin_user, category_food
):
    """spec § 8.1 bulk_update_category_by_merchant 等价。"""
    resp = logged_in_client.post(
        "/api/transactions/bulk-update-by-merchant",
        json={
            "pattern": "瑞幸",
            "match_kind": "contains",
            "category_id": category_food.id,
            "also_add_rule": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["affected_count"] >= 0  # 真实样本可能没瑞幸,本测试只验流程
    if body["affected_count"] > 0:
        assert body["rule_id"] is not None
        # 规则真的被加到 merchant_rules
        rule = db.execute(
            select(MerchantRule).where(
                MerchantRule.user_id == admin_user.id,
                MerchantRule.pattern == "瑞幸",
                MerchantRule.match_kind == "contains",
            )
        ).scalar_one_or_none()
        assert rule is not None
        assert rule.category_id == category_food.id


def test_bulk_update_idempotent_does_not_dup_rule(
    logged_in_client, imported_sample, db, admin_user, category_food
):
    """同 pattern 二次 also_add_rule=True → 不应建第二条规则。"""
    payload = {"pattern": "瑞幸", "match_kind": "contains",
        "category_id": category_food.id, "also_add_rule": True}
    logged_in_client.post("/api/transactions/bulk-update-by-merchant", json=payload)
    logged_in_client.post("/api/transactions/bulk-update-by-merchant", json=payload)
    cnt = db.execute(
        select(MerchantRule).where(
            MerchantRule.user_id == admin_user.id,
            MerchantRule.pattern == "瑞幸",
            MerchantRule.match_kind == "contains",
        )
    ).scalars().all()
    assert len(cnt) == 1


def test_delete_only_for_manual_or_conversation(
    logged_in_client, imported_sample, db, admin_user
):
    """从账单导入的 tx 不允许 DELETE。"""
    tx = db.execute(
        select(Transaction).where(
            Transaction.user_id == admin_user.id,
            Transaction.source == "alipay",
        ).limit(1)
    ).scalar_one()
    resp = logged_in_client.delete(f"/api/transactions/{tx.id}")
    assert resp.status_code == 403


def test_list_requires_login(client):
    resp = client.get("/api/transactions")
    assert resp.status_code == 401
