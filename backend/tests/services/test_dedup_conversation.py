"""⑤ 对话↔账单 — spec § 6.5。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Account, Transaction, User
from app.services.dedup import conversation_match


@pytest.fixture
def env(db):
    user = User(username="dc", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    ali = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add(ali); db.flush()
    return user, ali


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


def test_conversation_matches_alipay_pending(db, env):
    user, ali = env
    c = _add(db, user_id=user.id, account_id=ali.id, source="conversation",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 30), merchant="瑞幸咖啡 北京")

    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    db.flush()

    assert len(pairs) == 1
    p = pairs[0]
    assert p.match_kind == "conversation"
    assert p.status == "pending"
    assert p.primary_tx_id in {c.id, a.id}
    assert p.mirror_tx_id in {c.id, a.id}


def test_no_conversation_no_op(db, env):
    user, ali = env
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    assert pairs == []


def test_low_ratio_no_pair(db, env):
    user, ali = env
    _add(db, user_id=user.id, account_id=ali.id, source="conversation",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="完全无关 X")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="星巴克咖啡")
    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    assert pairs == []


def test_amount_mismatch_no_pair(db, env):
    user, ali = env
    _add(db, user_id=user.id, account_id=ali.id, source="conversation",
        amount="14.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    assert pairs == []
