"""run_dedup_pass 串起 ②③④⑤,确保各信号正确触发不冲突。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Account, Transaction, User
from app.services.dedup import run_dedup_pass


@pytest.fixture
def env(db):
    user = User(username="dr", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    bank = Account(user_id=user.id, name="ccb", type="bank_credit",
        institution="建设银行", last4="7432")
    ali = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    we = Account(user_id=user.id, name="微信", type="wechat",
        institution="微信支付", last4=None)
    db.add_all([bank, ali, we]); db.flush()
    return user, bank, ali, we


def _add(db, *, user_id, account_id, source, amount, t, merchant,
         ext=None, payment_method=None):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=t, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=ext,
        payment_method_raw=payment_method, is_mirror=False,
        source_unique_key=f"{source}:{ext or merchant}-{t.isoformat()}",
    )
    db.add(tx); db.flush()
    return tx


def test_run_dedup_pass_handles_all_four_signals(db, env):
    """场景:微信→建行 锚定 + 支付宝→交行 桥接(无;此场景重点 ②/③)。"""
    user, bank, ali, we = env
    # 微信 + 建行(应被 ② 锚定)
    bank_tx = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="20.00", t=datetime(2026, 3, 1, 13, 0), merchant="瑞幸咖啡 7432")
    we_tx = _add(db, user_id=user.id, account_id=we.id, source="wechat",
        amount="20.00", t=datetime(2026, 3, 1, 12, 0),
        payment_method="建设银行信用卡(7432)", merchant="瑞幸咖啡")

    # 支付宝 + 另一笔建行(强重复,但金额不同所以不命中)
    _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="50.00", t=datetime(2026, 3, 2, 9, 0), merchant="星巴克")

    pairs = run_dedup_pass(db, user_id=user.id, new_tx_ids=[bank_tx.id, we_tx.id])
    db.flush()

    # 至少有 1 个 strong/confirmed pair(微信→银行锚定)
    assert any(p.match_kind == "strong" and p.status == "confirmed" for p in pairs)
    db.refresh(bank_tx); db.refresh(we_tx)
    assert bank_tx.is_mirror is True
    assert we_tx.is_mirror is False


def test_run_dedup_pass_empty_input(db, env):
    user, _, _, _ = env
    pairs = run_dedup_pass(db, user_id=user.id, new_tx_ids=[])
    assert pairs == []
