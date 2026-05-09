"""④ 桥接(支付宝→银行) — spec § 6.4。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, Transaction, User
from app.services.dedup import bridge_alipay_to_bank


@pytest.fixture
def env(db):
    user = User(username="db", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    bank = Account(user_id=user.id, name="bocom", type="bank_debit",
        institution="交通银行", last4="2498")
    ali = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", last4=None)
    db.add_all([bank, ali]); db.flush()
    return user, bank, ali


def _add(db, *, user_id, account_id, source, amount, t, merchant, ext=None):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=t, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=ext, is_mirror=False,
        source_unique_key=f"{source}:{ext or merchant}-{t.isoformat()}",
    )
    db.add(tx); db.flush()
    return tx


def test_single_alipay_matches_bank_amount_pending(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="42.00", t=datetime(2026, 3, 1, 14, 0),
        merchant="拉扎斯网络科技-饿了么")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="42.00", t=datetime(2026, 3, 1, 13, 0), merchant="某餐厅")

    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    db.flush()

    assert len(pairs) == 1
    p = pairs[0]
    assert p.match_kind == "bridge"
    assert p.status == "pending"
    assert p.primary_tx_id == a.id
    assert p.mirror_tx_id == b.id
    assert 0.8 <= p.confidence <= 0.9


def test_aggregate_two_alipay_match_one_bank(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="100.00", t=datetime(2026, 3, 2, 10, 0), merchant="蚂蚁(杭州)网络")
    a1 = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="60.00", t=datetime(2026, 3, 1, 18, 0), merchant="餐A", ext="a1")
    a2 = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="40.00", t=datetime(2026, 3, 1, 19, 0), merchant="超市B", ext="a2")

    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    db.flush()

    # 贪心聚合 60+40=100 → 两个 pending pair
    assert len(pairs) == 2
    for p in pairs:
        assert p.match_kind == "bridge"
        assert p.status == "pending"
        assert p.confidence < 0.8  # 聚合置信度低于单笔


def test_no_bridge_keyword_no_op(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="20.00", t=datetime(2026, 3, 1, 12, 0), merchant="超市POS消费")
    _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="20.00", t=datetime(2026, 3, 1, 12, 0), merchant="X")
    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    assert pairs == []


def test_no_alipay_match_in_window(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="77.00", t=datetime(2026, 3, 1, 12, 0), merchant="支付宝代扣")
    _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="77.00", t=datetime(2026, 3, 5, 12, 0), merchant="X")  # 4 天后
    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    assert pairs == []


def test_skips_already_mirror_alipay(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="33.00", t=datetime(2026, 3, 1, 12, 0), merchant="财付通-X")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="33.00", t=datetime(2026, 3, 1, 12, 0), merchant="X")
    a.is_mirror = True; db.flush()
    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    assert pairs == []
