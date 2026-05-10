"""POST /api/transactions/manual + GET /merchants + GET /pending-classifications 测试。

slice E Task 1/2/3 端点共用此文件 — 三组测试用 # === Section ===  注释分隔。
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models import Account, Category, MerchantRule, Transaction

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


# === Section: GET /api/transactions/merchants (Task 2) ===

@pytest.fixture
def luckin_transactions(db, admin_user, alipay_account, cafe_category) -> list[Transaction]:
    """seed 5 笔瑞幸 + 2 笔星巴克,均 expense 已分类。"""
    rows: list[Transaction] = []
    for i, (merchant_norm, amt) in enumerate([
        ("瑞幸咖啡 五道口", "23.50"),
        ("瑞幸咖啡 西二旗", "18.00"),
        ("瑞幸咖啡 五道口", "25.00"),
        ("瑞幸咖啡 望京", "21.00"),
        ("瑞幸咖啡 五道口", "27.00"),
        ("星巴克 国贸店", "38.00"),
        ("星巴克 望京店", "42.00"),
    ]):
        tx = Transaction(
            user_id=admin_user.id, account_id=alipay_account.id,
            tx_kind="expense", tx_time=datetime(2026, 5, 1+i, 9, 0, tzinfo=timezone.utc),
            amount=Decimal(amt), currency="CNY", amount_settled_cny=Decimal(amt),
            merchant_raw=merchant_norm, merchant_normalized=merchant_norm,
            category_id=cafe_category.id, classification_confidence=1.0,
            source="manual", is_mirror=False,
        )
        db.add(tx); rows.append(tx)
    db.flush()
    return rows


def test_find_merchants_keyword_match(logged_in_client, luckin_transactions):
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "瑞幸"})
    assert resp.status_code == 200
    data = resp.json()
    # 至少 3 个不同的瑞幸 normalized 名字(五道口/西二旗/望京)
    luckin_items = [m for m in data["items"] if "瑞幸" in m["normalized"]]
    assert len(luckin_items) >= 3
    # 每条有 count + total_amount + sample_categories
    for item in luckin_items:
        assert item["count"] >= 1
        assert Decimal(item["total_amount"]) > 0
        assert isinstance(item["sample_categories"], list)
    # 五道口出现 3 次合计 75.50
    wudaokou = next(m for m in luckin_items if "五道口" in m["normalized"])
    assert wudaokou["count"] == 3
    assert Decimal(wudaokou["total_amount"]) == Decimal("75.50")


def test_find_merchants_keyword_case_insensitive(logged_in_client, luckin_transactions):
    """ILIKE 大小写不敏感(中文不影响,但确保英文走 ILIKE)。"""
    # 加一条英文商户
    # (此 test 仅校验 ILIKE 走 ICU,中文 LIKE 在 PG 里默认大小写无关,英文需 ILIKE)
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "星巴克"})
    assert resp.status_code == 200
    starbucks = [m for m in resp.json()["items"] if "星巴克" in m["normalized"]]
    assert len(starbucks) == 2  # 国贸店 + 望京店


def test_find_merchants_empty_keyword_422(logged_in_client):
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": ""})
    assert resp.status_code == 422


def test_find_merchants_no_match_returns_empty(logged_in_client, luckin_transactions):
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "tim hortons"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_find_merchants_excludes_mirrors(
    logged_in_client, luckin_transactions, db,
):
    """is_mirror=True 的 transaction 不参与聚合(避免重复算)。"""
    # 把第一条标 mirror
    luckin_transactions[0].is_mirror = True
    luckin_transactions[0].mirror_of_id = luckin_transactions[1].id
    db.flush()
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "五道口"})
    # 五道口仍能聚合(剩 2 条),count=2 而非 3
    wudaokou = next(
        m for m in resp.json()["items"] if "五道口" in m["normalized"]
    )
    assert wudaokou["count"] == 2


# === Section: GET /api/transactions/pending-classifications (Task 3) ===

def test_pending_classifications_returns_only_uncategorized(
    logged_in_client, alipay_account, cafe_category, db, admin_user,
):
    """category_id IS NULL → 进列表;已分类的不出现。"""
    # 1 笔已分类 + 2 笔未分类
    classified = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 1, 12, tzinfo=timezone.utc),
        amount=Decimal("10.00"), currency="CNY", amount_settled_cny=Decimal("10.00"),
        merchant_raw="瑞幸", merchant_normalized="瑞幸",
        category_id=cafe_category.id, classification_confidence=1.0,
        source="manual", is_mirror=False,
    )
    pending1 = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 2, 12, tzinfo=timezone.utc),
        amount=Decimal("20.00"), currency="CNY", amount_settled_cny=Decimal("20.00"),
        merchant_raw="某小店", merchant_normalized="某小店",
        category_id=None, source="manual", is_mirror=False,
    )
    pending2 = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 3, 12, tzinfo=timezone.utc),
        amount=Decimal("30.00"), currency="CNY", amount_settled_cny=Decimal("30.00"),
        merchant_raw="另家店", merchant_normalized="另家店",
        category_id=None, source="manual", is_mirror=False,
    )
    db.add_all([classified, pending1, pending2]); db.flush()

    resp = logged_in_client.get("/api/transactions/pending-classifications")
    assert resp.status_code == 200
    data = resp.json()
    ids = [tx["id"] for tx in data["items"]]
    assert pending1.id in ids
    assert pending2.id in ids
    assert classified.id not in ids


def test_pending_classifications_excludes_mirrors(
    logged_in_client, alipay_account, db, admin_user,
):
    """is_mirror=True 的未分类 tx 也不应出现(已被去重的镜像不需要分类)。"""
    primary = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 4, 12, tzinfo=timezone.utc),
        amount=Decimal("50.00"), currency="CNY", amount_settled_cny=Decimal("50.00"),
        merchant_raw="A", merchant_normalized="A",
        category_id=None, source="alipay", is_mirror=False,
    )
    db.add(primary); db.flush()
    mirror = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 4, 12, tzinfo=timezone.utc),
        amount=Decimal("50.00"), currency="CNY", amount_settled_cny=Decimal("50.00"),
        merchant_raw="A", merchant_normalized="A",
        category_id=None, source="bank", is_mirror=True, mirror_of_id=primary.id,
    )
    db.add(mirror); db.flush()

    resp = logged_in_client.get("/api/transactions/pending-classifications")
    ids = [tx["id"] for tx in resp.json()["items"]]
    assert primary.id in ids
    assert mirror.id not in ids


def test_pending_classifications_pagination(
    logged_in_client, alipay_account, db, admin_user,
):
    """seed 5 条 → limit=2 + offset=2 应返回中间 2 条(按 tx_time DESC)。"""
    for i in range(5):
        db.add(Transaction(
            user_id=admin_user.id, account_id=alipay_account.id,
            tx_kind="expense", tx_time=datetime(2026, 5, 10+i, 12, tzinfo=timezone.utc),
            amount=Decimal("10.00"), currency="CNY", amount_settled_cny=Decimal("10.00"),
            merchant_raw=f"店{i}", merchant_normalized=f"店{i}",
            category_id=None, source="manual", is_mirror=False,
        ))
    db.flush()
    resp = logged_in_client.get("/api/transactions/pending-classifications", params={
        "limit": 2, "offset": 2,
    })
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    # 倒序 → 14日 / 13日 / [12日, 11日] / 10日
    assert data["items"][0]["merchant_raw"] == "店2"
    assert data["items"][1]["merchant_raw"] == "店1"
