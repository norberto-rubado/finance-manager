"""persist_raw_transactions 测试 — merchant_normalized / source_unique_key / 同源 dedup。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, StatementImport, Transaction, User
from app.services.importer import persist_raw_transactions
from app.services.statement_parser import AccountHint, ParseResult, RawTransaction


@pytest.fixture
def env(db):
    """造 user + account + statement_import。"""
    user = User(username="px", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    acc = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", last4=None)
    db.add(acc)
    db.flush()
    si = StatementImport(
        user_id=user.id, account_id=acc.id,
        source_type="alipay_csv", filename="x.csv", file_hash="h" * 64,
        period_start=datetime(2026, 3, 1), period_end=datetime(2026, 3, 26),
        raw_row_count=0, imported_count=0, deduped_count=0, classified_count=0,
    )
    db.add(si)
    db.flush()
    return user, acc, si


def _raw(merchant="瑞幸咖啡(北京)", amount="12.50", external_id="2026030122000001", **kw):
    return RawTransaction(
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        post_time=None,
        amount=Decimal(amount),
        currency="CNY",
        amount_settled_cny=Decimal(amount),
        tx_kind=kw.get("tx_kind", "expense"),
        merchant_raw=merchant,
        counterparty_raw=None,
        description_raw=None,
        external_tx_id=external_id,
        external_merchant_id=None,
        payment_method_raw=kw.get("payment_method_raw"),
        raw_row=kw.get("raw_row", {"raw": "row"}),
    )


def test_persist_creates_rows_with_normalized_merchant(db, env):
    user, acc, si = env
    raws = [_raw(), _raw(merchant="星巴克(上海)", external_id="2026030122000002")]
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=raws,
    )
    db.flush()
    assert created == 2 and skipped == 0
    txs = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalars().all()
    merchants_norm = sorted(t.merchant_normalized for t in txs)
    assert merchants_norm == ["星巴克", "瑞幸咖啡"]


def test_persist_uses_source_unique_key_with_external_id(db, env):
    user, acc, si = env
    raws = [_raw(external_id="abc123")]
    persist_raw_transactions(db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=raws)
    db.flush()
    tx = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalar_one()
    assert tx.source_unique_key == "alipay:abc123"
    assert tx.source == "alipay"


def test_persist_skips_duplicate_source_unique_key_in_same_batch(db, env):
    """spec § 6.1 ①:同 file 内含同 external_tx_id → 跳过第二条。"""
    user, acc, si = env
    raws = [_raw(external_id="dup1"), _raw(external_id="dup1", merchant="不同商家")]
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=raws,
    )
    db.flush()
    assert created == 1 and skipped == 1


def test_persist_skips_when_source_unique_key_already_in_db(db, env):
    """重复导入(应被 file_hash 拦,但万一漏过) → external_tx_id 唯一约束兜底。"""
    user, acc, si = env
    persist_raw_transactions(db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=[_raw(external_id="seen1")])
    db.flush()
    # 再来一次相同 external_id
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=[_raw(external_id="seen1")],
    )
    db.flush()
    assert created == 0 and skipped == 1


def test_persist_synthesizes_unique_key_when_external_id_missing(db, env):
    """external_tx_id 为 None(银行 PDF 常见)→ 用 (statement_import_id, row_idx, hash) 合成。"""
    user, acc, si = env
    raws = [_raw(external_id=None, merchant="商家A"),
            _raw(external_id=None, merchant="商家B")]
    created, _ = persist_raw_transactions(db, user_id=user.id, account_id=acc.id,
        statement_import_id=si.id, source_type="bank_pdf_bocom_debit", raw_transactions=raws)
    db.flush()
    txs = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalars().all()
    assert created == 2
    keys = sorted(t.source_unique_key for t in txs)
    # 两条 key 都以 "bank:" 开头,互不相同(包含 row_idx 防撞)
    assert all(k.startswith("bank:") for k in keys)
    assert len(set(keys)) == 2


def test_persist_source_mapping(db, env):
    """source_type → source 派生:alipay_csv → alipay, bank_pdf_* → bank。"""
    user, acc, si = env
    cases = [
        ("alipay_csv", "alipay"),
        ("wechat_xlsx", "wechat"),
        ("bank_pdf_bocom_debit", "bank"),
        ("bank_pdf_ccb_credit", "bank"),
    ]
    for stype, expected_src in cases:
        # 用不同 external_id 避免跨 case 撞 unique
        persist_raw_transactions(
            db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
            source_type=stype,
            raw_transactions=[_raw(external_id=f"ex-{stype}", merchant=f"M-{stype}")],
        )
    db.flush()
    rows = db.execute(select(Transaction.source_unique_key, Transaction.source)
                      .where(Transaction.user_id == user.id)).all()
    by_key = dict(rows)
    assert "alipay" in {by_key[k] for k in by_key if k.startswith("alipay:")}
    assert "bank" in {by_key[k] for k in by_key if k.startswith("bank:")}


def test_persist_preserves_raw_payload_and_payment_method(db, env):
    user, acc, si = env
    raws = [_raw(payment_method_raw="建设银行信用卡(7432)",
                 raw_row={"col1": "v1", "col2": "v2"})]
    persist_raw_transactions(db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="wechat_xlsx", raw_transactions=raws)
    db.flush()
    tx = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalar_one()
    assert tx.payment_method_raw == "建设银行信用卡(7432)"
    assert tx.raw_payload == {"col1": "v1", "col2": "v2"}


def test_persist_empty_list_returns_0_0(db, env):
    user, acc, si = env
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=[],
    )
    assert created == 0 and skipped == 0
