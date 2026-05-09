"""② 微信→银行精确锚定 dedup 测试 — spec § 6.2。"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, StatementImport, Transaction, User
from app.services.dedup import wechat_to_bank_anchor


@pytest.fixture
def env(db):
    user = User(username="dx", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    bank_acc = Account(user_id=user.id, name="建行信用卡 7432",
        type="bank_credit", institution="建设银行", last4="7432")
    wechat_acc = Account(user_id=user.id, name="微信支付", type="wechat",
        institution="微信支付", last4=None)
    db.add_all([bank_acc, wechat_acc])
    db.flush()
    return user, bank_acc, wechat_acc


def _add_tx(db, *, user_id, account_id, source, amount, tx_time,
            external_id=None, payment_method=None, merchant="X"):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=tx_time, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=external_id,
        payment_method_raw=payment_method, is_mirror=False,
        source_unique_key=f"{source}:{external_id or merchant}",
    )
    db.add(tx)
    db.flush()
    return tx


def test_wechat_anchors_unique_bank_tx(db, env):
    user, bank_acc, wechat_acc = env
    bank_tx = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="12.50",
        tx_time=datetime(2026, 3, 1, 14, 0, 0), merchant="瑞幸咖啡")
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="12.50",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="瑞幸咖啡")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    db.flush()

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.match_kind == "strong"
    assert pair.status == "confirmed"
    assert pair.confidence >= 0.95

    db.refresh(bank_tx)
    db.refresh(wechat_tx)
    assert bank_tx.is_mirror is True
    assert bank_tx.mirror_of_id == wechat_tx.id
    assert wechat_tx.is_mirror is False


def test_wechat_no_bank_match_no_op(db, env):
    """微信交易在 ±1d / 同 last4 / 同金额下找不到银行,不动。"""
    user, _, wechat_acc = env
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="99.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="无对应银行交易")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []
    db.refresh(wechat_tx)
    assert wechat_tx.is_mirror is False


def test_wechat_no_payment_method_skipped(db, env):
    """payment_method_raw 不含 4 位数字(零钱付),跳过。"""
    user, _, wechat_acc = env
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="5.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="零钱", merchant="街边小摊")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []


def test_wechat_multiple_bank_matches_pending(db, env):
    """同 day + last4 + amount 命中多条 bank 交易 → pending,等待人工。"""
    user, bank_acc, wechat_acc = env
    bank1 = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="50.00",
        tx_time=datetime(2026, 3, 1, 10, 0, 0), merchant="A", external_id="b1")
    bank2 = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="50.00",
        tx_time=datetime(2026, 3, 1, 16, 0, 0), merchant="B", external_id="b2")
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="50.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="C", external_id="w1")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    db.flush()

    # 多匹配 → 不写镜像,但写 pending pair(让用户在 review 页选)
    assert len(pairs) >= 2  # 一个微信对应两个 bank 候选,各开 pending pair
    for p in pairs:
        assert p.status == "pending"
        assert p.match_kind == "strong"
    db.refresh(bank1)
    db.refresh(bank2)
    assert bank1.is_mirror is False
    assert bank2.is_mirror is False


def test_wechat_outside_1d_window_no_match(db, env):
    """银行交易在 ±1d 之外,不匹配。"""
    user, bank_acc, wechat_acc = env
    _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="20.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0), merchant="远古交易")
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="20.00",
        tx_time=datetime(2026, 3, 5, 12, 0, 0),  # 4 天后
        payment_method="建设银行信用卡(7432)", merchant="今日新交易")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []


def test_wechat_anchor_skips_bank_already_mirror(db, env):
    """已经被标 is_mirror 的银行交易不应再被认领。"""
    user, bank_acc, wechat_acc = env
    bank_tx = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="30.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0), merchant="X")
    bank_tx.is_mirror = True
    db.flush()

    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="30.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="Y")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []
