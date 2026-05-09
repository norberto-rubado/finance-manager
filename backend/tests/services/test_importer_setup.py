"""importer setup 函数单元测试 — file_hash / ensure_account / ensure_statement_import。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, StatementImport, User
from app.services.importer import (
    DuplicateImportError,
    ensure_account_for_hint,
    ensure_statement_import,
    file_sha256,
)
from app.services.statement_parser import AccountHint, ParseResult, RawTransaction


@pytest.fixture
def test_user(db) -> User:
    u = User(username="ix", password_hash="$2b$12$" + "x" * 53)
    db.add(u)
    db.flush()
    return u


def test_file_sha256_deterministic():
    assert file_sha256(b"hello") == file_sha256(b"hello")
    assert file_sha256(b"hello") != file_sha256(b"world")
    assert len(file_sha256(b"hello")) == 64  # hex digest


def test_ensure_account_creates_for_bank_credit(db, test_user):
    hint = AccountHint(type="bank_credit", institution="建设银行", last4="7432")
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert acc.id is not None
    assert acc.institution == "建设银行"
    assert acc.last4 == "7432"
    assert acc.type == "bank_credit"
    assert acc.name == "建设银行信用卡 7432"  # 自动起名


def test_ensure_account_creates_for_bank_debit(db, test_user):
    hint = AccountHint(type="bank_debit", institution="交通银行", last4="2498")
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert acc.name == "交通银行借记卡 2498"


def test_ensure_account_idempotent_same_hint(db, test_user):
    hint = AccountHint(type="bank_credit", institution="建设银行", last4="7432")
    a1 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    a2 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert a1.id == a2.id


def test_ensure_account_alipay_global(db, test_user):
    """支付宝/微信无 last4,固定全局账户(last4 IS NULL)。"""
    hint = AccountHint(type="alipay", institution="支付宝", last4=None)
    a1 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    a2 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert a1.id == a2.id
    assert a1.last4 is None
    assert a1.name == "支付宝"


def test_ensure_account_wechat_global(db, test_user):
    hint = AccountHint(type="wechat", institution="微信支付", last4=None)
    a = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert a.name == "微信支付"
    assert a.type == "wechat"


def test_ensure_account_different_last4_creates_separate(db, test_user):
    """同 institution 不同 last4 → 不同 account。"""
    a1 = ensure_account_for_hint(db, test_user.id,
        AccountHint(type="bank_debit", institution="交通银行", last4="2498"))
    a2 = ensure_account_for_hint(db, test_user.id,
        AccountHint(type="bank_debit", institution="交通银行", last4="9999"))
    db.flush()
    assert a1.id != a2.id


def _make_parse_result(account_hint: AccountHint, raw_count: int = 10) -> ParseResult:
    return ParseResult(
        raw_transactions=[],
        account_hint=account_hint,
        period_start=datetime(2026, 3, 1),
        period_end=datetime(2026, 3, 26),
        metadata={"raw_row_count": raw_count, "imported_count": raw_count, "dropped_count": 0},
    )


def test_ensure_statement_import_creates_row(db, test_user):
    hint = AccountHint(type="alipay", institution="支付宝", last4=None)
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    pr = _make_parse_result(hint, raw_count=42)
    si = ensure_statement_import(
        db, user_id=test_user.id, account_id=acc.id,
        source_type="alipay_csv",
        filename="alipay_x.csv",
        file_hash="a" * 64,
        parse_result=pr,
    )
    db.flush()
    assert si.id is not None
    assert si.source_type == "alipay_csv"
    assert si.raw_row_count == 42
    assert si.period_start == datetime(2026, 3, 1)


def test_ensure_statement_import_rejects_duplicate_hash(db, test_user):
    hint = AccountHint(type="alipay", institution="支付宝", last4=None)
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    pr = _make_parse_result(hint)
    h = "b" * 64
    ensure_statement_import(db, user_id=test_user.id, account_id=acc.id,
        source_type="alipay_csv", filename="x.csv", file_hash=h, parse_result=pr)
    db.flush()
    with pytest.raises(DuplicateImportError) as ei:
        ensure_statement_import(db, user_id=test_user.id, account_id=acc.id,
            source_type="alipay_csv", filename="x_v2.csv", file_hash=h, parse_result=pr)
    assert "already imported" in str(ei.value).lower()
