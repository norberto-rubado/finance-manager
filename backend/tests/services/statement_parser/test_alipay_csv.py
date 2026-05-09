"""支付宝 CSV 解析器测试。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.alipay_csv import AlipayCsvParser
from app.services.statement_parser.base import RawTransaction


@pytest.fixture(scope="module")
def parser() -> AlipayCsvParser:
    return AlipayCsvParser()


@pytest.fixture(scope="module")
def parsed(parser: AlipayCsvParser, alipay_csv_bytes: bytes):
    return parser.parse(alipay_csv_bytes)


def test_source_type(parser: AlipayCsvParser):
    assert parser.source_type == "alipay_csv"


def test_detect_accepts_real_alipay_csv(
    parser: AlipayCsvParser, alipay_csv_bytes: bytes, alipay_filename: str
):
    assert parser.detect(alipay_csv_bytes, alipay_filename) is True


def test_detect_rejects_non_csv(parser: AlipayCsvParser):
    assert parser.detect(b"%PDF-1.4\n%fake", "x.pdf") is False
    assert parser.detect(b"not csv at all", "x.txt") is False


def test_detect_rejects_other_csv_without_alipay_marker(parser: AlipayCsvParser):
    """普通 utf-8 csv 不应被错认。"""
    fake = "date,amount\n2026-01-01,100\n".encode("utf-8")
    assert parser.detect(fake, "other.csv") is False


def test_parse_returns_at_least_some_transactions(parsed):
    assert len(parsed.raw_transactions) >= 1, "支付宝样本至少有一行交易成功"


def test_parse_account_hint_is_alipay(parsed):
    h = parsed.account_hint
    assert h.type == "alipay"
    assert h.institution == "支付宝"
    assert h.last4 is None


def test_parse_period_in_2026_q1(parsed):
    """样本日期范围 20260326 期间,period_end 应在 3 月。"""
    assert parsed.period_start <= parsed.period_end
    assert 2025 <= parsed.period_start.year <= 2026


def test_parse_filters_out_non_success(parsed, parser, alipay_csv_bytes):
    """所有产出交易必须 raw_row['交易状态'] == '交易成功'。"""
    for tx in parsed.raw_transactions:
        assert tx.raw_row.get("交易状态", "").strip() == "交易成功"


def test_parse_amounts_are_positive_decimals(parsed):
    for tx in parsed.raw_transactions:
        assert isinstance(tx.amount, Decimal)
        assert tx.amount > 0
        # 支付宝不暴露外币,settled 与 amount 同值
        assert tx.amount_settled_cny == tx.amount
        assert tx.currency == "CNY"


def test_parse_tx_kind_inferred_from_inout(parsed):
    """收/支 列 → expense | income | neutral。"""
    kinds = {tx.tx_kind for tx in parsed.raw_transactions}
    assert kinds.issubset({"expense", "income", "neutral", "refund"})
    # 真实样本应至少有 expense
    assert "expense" in kinds


def test_parse_external_tx_id_populated(parsed):
    """支付宝交易号(列名"交易号")必须填到 external_tx_id。"""
    for tx in parsed.raw_transactions:
        assert tx.external_tx_id is not None
        assert len(tx.external_tx_id) > 8  # 支付宝交易号通常 28 位


def test_parse_payment_method_is_none(parsed):
    """支付宝 CSV 不暴露底层卡。"""
    for tx in parsed.raw_transactions:
        assert tx.payment_method_raw is None


def test_parse_first_transaction_has_merchant_and_time(parsed):
    """抽样:第一条交易必须有商家名 + tx_time。"""
    tx = parsed.raw_transactions[0]
    assert tx.merchant_raw  # 非空串
    assert isinstance(tx.tx_time, datetime)


def test_parse_metadata_has_row_count(parsed):
    """metadata 应记录原始行数和过滤后行数,便于 slice C 对账。"""
    md = parsed.metadata
    assert "raw_row_count" in md
    assert "imported_count" in md
    assert md["imported_count"] == len(parsed.raw_transactions)
    assert md["raw_row_count"] >= md["imported_count"]


def test_parse_raw_row_preserves_original_columns(parsed):
    """raw_row 应含支付宝原列名(中文表头),便于审计。"""
    tx = parsed.raw_transactions[0]
    assert "交易号" in tx.raw_row or "支付宝交易号" in tx.raw_row
    assert "金额" in str(tx.raw_row.keys()) or "金额（元）" in tx.raw_row


def test_parse_invalid_bytes_raises(parser: AlipayCsvParser):
    """乱码字节应 raise ValueError 而非吞错。"""
    with pytest.raises(ValueError):
        parser.parse(b"\x00\x01\x02 not a csv at all")
