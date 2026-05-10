"""compute_account_balances — 纯函数,流水推算 net balance per account。"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Transaction, User
from app.services.summary import compute_account_balances


@pytest.fixture
def user(db) -> User:
    u = User(username="balance_test", password_hash="$2b$12$x" + "y" * 50)
    db.add(u); db.flush(); return u


@pytest.fixture
def alipay(db, user) -> Account:
    a = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", currency="CNY")
    db.add(a); db.flush(); return a


@pytest.fixture
def bank(db, user) -> Account:
    a = Account(user_id=user.id, name="交行借记 2498", type="bank_debit",
                institution="交通银行", last4="2498", currency="CNY")
    db.add(a); db.flush(); return a


def _tx(user_id, acc_id, kind, amt, when, *, mirror=False):
    return Transaction(
        user_id=user_id, account_id=acc_id, tx_kind=kind,
        tx_time=when, amount=Decimal(amt), currency="CNY",
        amount_settled_cny=Decimal(amt),
        merchant_raw="x", merchant_normalized="x",
        source="manual", is_mirror=mirror,
    )


def test_balance_simple_expense_minus_income(db, user, alipay):
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "300.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "150.50",
               datetime(2026, 5, 3, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("549.50")
    assert by_id[alipay.id]["latest_balance_at"] == datetime(2026, 5, 3, tzinfo=timezone.utc)


def test_balance_refund_subtracts(db, user, alipay):
    """refund 等同于 expense 的反向,从余额扣(spec 语义:已收回部分,不应当成 income)。

    实现选择:refund 与 expense 同号(都减),保持现有 importer 落库语义不变。
    """
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "200.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "refund", "50.00",
               datetime(2026, 5, 3, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    # 1000 - 200 - 50 = 750
    assert by_id[alipay.id]["latest_balance"] == Decimal("750.00")


def test_balance_neutral_excluded(db, user, alipay):
    """neutral(信用卡还款等)既不是 expense 也不是 income,**不算入余额**。"""
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "neutral", "500.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("1000.00")
    # neutral 仍参与 latest_balance_at 计算
    assert by_id[alipay.id]["latest_balance_at"] == datetime(2026, 5, 2, tzinfo=timezone.utc)


def test_balance_excludes_mirrors(db, user, alipay):
    """is_mirror=True 不参与流水累计。"""
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "200.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc), mirror=True))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("1000.00")


def test_balance_returns_zero_for_account_with_no_tx(db, user, alipay, bank):
    """alipay 有交易,bank 无交易;两个 account 都返回(bank balance=0,latest_balance_at=None)。"""
    db.add(_tx(user.id, alipay.id, "income", "100.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("100.00")
    assert by_id[bank.id]["latest_balance"] == Decimal("0.00")
    assert by_id[bank.id]["latest_balance_at"] is None


def test_balance_per_user_isolation(db, user, alipay):
    """另一个 user 的交易不影响本 user。"""
    other = User(username="other_test", password_hash="$2b$12$x" + "z" * 50)
    db.add(other); db.flush()
    other_acc = Account(user_id=other.id, name="o", type="alipay", currency="CNY")
    db.add(other_acc); db.flush()
    db.add(_tx(other.id, other_acc.id, "income", "999999.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "income", "100.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    # 只返回 user 的 accounts
    assert all(r["account_id"] in (alipay.id,) for r in result)
