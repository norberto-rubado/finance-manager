"""Dedup API e2e。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, Transaction


@pytest.fixture
def pending_pair(db, admin_user):
    """造一个 pending bridge pair(两条 tx + 一条 dedup_candidates)。"""
    bank = Account(user_id=admin_user.id, name="bocom", type="bank_debit",
        institution="交通银行", last4="2498")
    ali = Account(user_id=admin_user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add_all([bank, ali]); db.flush()
    a = Transaction(user_id=admin_user.id, account_id=ali.id, statement_import_id=None,
        tx_kind="expense", tx_time=datetime(2026, 3, 1, 12, 0),
        amount=Decimal("42.00"), currency="CNY", amount_settled_cny=Decimal("42.00"),
        merchant_raw="X", merchant_normalized="X", source="alipay",
        external_tx_id="a1", is_mirror=False, source_unique_key="alipay:a1")
    b = Transaction(user_id=admin_user.id, account_id=bank.id, statement_import_id=None,
        tx_kind="expense", tx_time=datetime(2026, 3, 1, 13, 0),
        amount=Decimal("42.00"), currency="CNY", amount_settled_cny=Decimal("42.00"),
        merchant_raw="拉扎斯", merchant_normalized="拉扎斯", source="bank",
        external_tx_id=None, is_mirror=False, source_unique_key="bank:b1")
    db.add_all([a, b]); db.flush()
    pair = DedupCandidate(user_id=admin_user.id, primary_tx_id=a.id, mirror_tx_id=b.id,
        match_kind="bridge", confidence=0.85, status="pending",
        reasoning={"rule": "test"})
    db.add(pair); db.flush()
    return pair, a, b


def test_list_pending_returns_pair(logged_in_client, pending_pair):
    pair, _, _ = pending_pair
    resp = logged_in_client.get("/api/dedup/pending")
    assert resp.status_code == 200
    body = resp.json()
    ids = [p["id"] for p in body["items"]]
    assert pair.id in ids


def test_confirm_pair_marks_mirror(logged_in_client, db, pending_pair):
    pair, a, b = pending_pair
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/confirm",
        json={"action": "confirm"})
    assert resp.status_code == 200
    db.refresh(pair); db.refresh(a); db.refresh(b)
    assert pair.status == "confirmed"
    assert pair.decided_at is not None
    assert b.is_mirror is True
    assert b.mirror_of_id == a.id


def test_reject_pair_keeps_both_tx_visible(logged_in_client, db, pending_pair):
    pair, a, b = pending_pair
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/confirm",
        json={"action": "reject"})
    assert resp.status_code == 200
    db.refresh(pair); db.refresh(b)
    assert pair.status == "rejected"
    assert b.is_mirror is False  # 不标镜像


def test_reject_endpoint_alias(logged_in_client, db, pending_pair):
    """POST /api/dedup/{id}/reject 是 confirm with action=reject 的语法糖。"""
    pair, a, b = pending_pair
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/reject", json={})
    assert resp.status_code == 200
    db.refresh(pair)
    assert pair.status == "rejected"


def test_decide_already_decided_returns_409(logged_in_client, db, pending_pair):
    pair, _, _ = pending_pair
    pair.status = "confirmed"
    pair.decided_at = datetime.utcnow()
    db.flush()
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/confirm",
        json={"action": "confirm"})
    assert resp.status_code == 409


def test_decide_404(logged_in_client):
    resp = logged_in_client.post("/api/dedup/9999999/confirm",
        json={"action": "confirm"})
    assert resp.status_code == 404


def test_pending_list_requires_login(client):
    resp = client.get("/api/dedup/pending")
    assert resp.status_code == 401
