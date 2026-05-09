"""StatementParser 接口契约 + dataclass 形态测试。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
    StatementParser,
)


def test_raw_transaction_has_required_fields():
    tx = RawTransaction(
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        post_time=None,
        amount=Decimal("12.50"),
        currency="CNY",
        amount_settled_cny=Decimal("12.50"),
        tx_kind="expense",
        merchant_raw="瑞幸咖啡",
        counterparty_raw=None,
        description_raw=None,
        external_tx_id="2026030122000001",
        external_merchant_id=None,
        payment_method_raw=None,
        raw_row={"raw_col": "raw_val"},
    )
    assert tx.amount == Decimal("12.50")
    assert tx.tx_kind == "expense"
    assert tx.raw_row["raw_col"] == "raw_val"


def test_raw_transaction_amount_is_decimal_not_float():
    """金额必须用 Decimal 防浮点误差。"""
    tx = RawTransaction(
        tx_time=datetime(2026, 3, 1),
        post_time=None,
        amount=Decimal("0.1") + Decimal("0.2"),
        currency="CNY",
        amount_settled_cny=Decimal("0.30"),
        tx_kind="expense",
        merchant_raw="x",
        counterparty_raw=None,
        description_raw=None,
        external_tx_id=None,
        external_merchant_id=None,
        payment_method_raw=None,
        raw_row={},
    )
    assert tx.amount == Decimal("0.3")  # Decimal 加法精确


def test_account_hint_fields():
    h = AccountHint(type="bank_credit", institution="建设银行", last4="7432")
    assert h.type == "bank_credit"
    assert h.institution == "建设银行"
    assert h.last4 == "7432"


def test_account_hint_last4_optional_for_alipay_wechat():
    h = AccountHint(type="alipay", institution="支付宝", last4=None)
    assert h.last4 is None


def test_parse_result_carries_metadata():
    r = ParseResult(
        raw_transactions=[],
        account_hint=AccountHint(type="alipay", institution="支付宝", last4=None),
        period_start=datetime(2026, 3, 1),
        period_end=datetime(2026, 3, 26),
        metadata={"row_count_in_header": 100, "expense_total": "1234.56"},
    )
    assert r.metadata["row_count_in_header"] == 100
    assert r.period_start.month == 3


def test_statement_parser_is_protocol():
    """StatementParser 是 Protocol(structural typing),实现类无需显式继承。"""
    class Dummy:
        source_type = "dummy"
        def detect(self, file_bytes: bytes, filename: str) -> bool:
            return False
        def parse(self, file_bytes: bytes) -> ParseResult:
            return ParseResult(
                raw_transactions=[],
                account_hint=AccountHint(type="cash", institution="现金", last4=None),
                period_start=datetime(2026, 1, 1),
                period_end=datetime(2026, 1, 1),
                metadata={},
            )
    d: StatementParser = Dummy()  # 编译期 ok 即说明 Protocol 形态正确
    assert d.source_type == "dummy"
    assert d.detect(b"", "x") is False
