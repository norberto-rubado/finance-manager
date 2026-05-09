"""③ 强重复(跨源 ±1h ratio≥80) — spec § 6.3。"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, Transaction, User
from app.services.dedup import strong_dedup_cross_source


@pytest.fixture
def env(db):
    user = User(username="ds", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    bank_acc = Account(user_id=user.id, name="bocom", type="bank_debit",
        institution="交通银行", last4="2498")
    alipay_acc = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add_all([bank_acc, alipay_acc])
    db.flush()
    return user, bank_acc, alipay_acc


def _add(db, *, user_id, account_id, source, amount, t, merchant, ext=None):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=t, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=ext, is_mirror=False,
        source_unique_key=f"{source}:{ext or merchant}-{t.isoformat()}",
    )
    db.add(tx)
    db.flush()
    return tx


def test_cross_source_high_ratio_in_1h_pairs_confirmed(db, env):
    user, bank_acc, alipay_acc = env
    a = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="36.50", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    b = _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="36.50", t=datetime(2026, 3, 1, 12, 30), merchant="瑞幸咖啡 北京")

    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a.id, b.id])
    db.flush()

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.match_kind == "strong"
    assert pair.status == "confirmed"
    db.refresh(a); db.refresh(b)
    # bank 这条作 mirror(spec 默认银行滞后)
    assert b.is_mirror is True
    assert b.mirror_of_id == a.id


def test_outside_1h_no_pair(db, env):
    user, bank_acc, alipay_acc = env
    a = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="20.00", t=datetime(2026, 3, 1, 9, 0), merchant="星巴克")
    b = _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="20.00", t=datetime(2026, 3, 1, 11, 30), merchant="星巴克")  # 2.5h 差

    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a.id, b.id])
    assert pairs == []


def test_low_merchant_ratio_no_pair(db, env):
    user, bank_acc, alipay_acc = env
    _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="100.00", t=datetime(2026, 3, 1, 12, 0), merchant="北京烤鸭总店")
    _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="100.00", t=datetime(2026, 3, 1, 12, 10), merchant="深圳科技有限公司")
    new_ids = [t.id for t in db.execute(select(Transaction)).scalars().all()]
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=new_ids)
    # ratio 低,不该匹配
    assert pairs == []


def test_amount_mismatch_no_pair(db, env):
    user, bank_acc, alipay_acc = env
    _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="50.00", t=datetime(2026, 3, 1, 12, 0), merchant="美团")
    _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="50.01", t=datetime(2026, 3, 1, 12, 5), merchant="美团")
    new_ids = [t.id for t in db.execute(select(Transaction)).scalars().all()]
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=new_ids)
    assert pairs == []


def test_same_source_not_paired(db, env):
    """同 source 不应被本算法配对(由 ① external_tx_id 唯一约束处理)。"""
    user, _, alipay_acc = env
    a1 = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="10.00", t=datetime(2026, 3, 1, 12, 0), merchant="X", ext="e1")
    a2 = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="10.00", t=datetime(2026, 3, 1, 12, 30), merchant="X", ext="e2")
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a1.id, a2.id])
    assert pairs == []


def test_skips_already_mirror(db, env):
    user, bank_acc, alipay_acc = env
    a = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="11.00", t=datetime(2026, 3, 1, 12, 0), merchant="美团外卖")
    b = _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="11.00", t=datetime(2026, 3, 1, 12, 30), merchant="美团外卖")
    b.is_mirror = True  # 假装已被 ② 处理
    db.flush()
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a.id, b.id])
    assert pairs == []
