"""建行信用卡 PDF 解析器测试 — 重点验证 3 大边界 case。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.ccb_credit_pdf import CcbCreditPdfParser


@pytest.fixture(scope="module")
def parser() -> CcbCreditPdfParser:
    return CcbCreditPdfParser()


@pytest.fixture(scope="module")
def parsed(parser: CcbCreditPdfParser, ccb_credit_pdf_bytes: bytes):
    return parser.parse(ccb_credit_pdf_bytes)


def test_source_type(parser: CcbCreditPdfParser):
    assert parser.source_type == "bank_pdf_ccb_credit"


def test_detect_accepts_real_ccb_pdf(
    parser: CcbCreditPdfParser, ccb_credit_pdf_bytes: bytes, ccb_filename: str
):
    assert parser.detect(ccb_credit_pdf_bytes, ccb_filename) is True


def test_detect_rejects_bocom_pdf(
    parser: CcbCreditPdfParser, bocom_debit_pdf_bytes: bytes
):
    assert parser.detect(bocom_debit_pdf_bytes, "bocom.pdf") is False


def test_parse_yields_transactions(parsed):
    assert len(parsed.raw_transactions) >= 1


def test_parse_account_hint(parsed):
    h = parsed.account_hint
    assert h.type == "bank_credit"
    assert h.institution == "建设银行"  # 建设银行
    assert h.last4 == "7432"


def test_parse_amounts_positive_decimals(parsed):
    for tx in parsed.raw_transactions:
        assert isinstance(tx.amount, Decimal)
        assert tx.amount > 0
        assert isinstance(tx.amount_settled_cny, Decimal)
        assert tx.amount_settled_cny > 0


def test_parse_tx_time_format_yyyymmdd(parsed):
    """建行 PDF 日期格式 20260326 → 转 datetime 后年应为 2026 附近。"""
    for tx in parsed.raw_transactions[:5]:
        assert 2024 <= tx.tx_time.year <= 2026


def test_parse_post_time_populated(parsed):
    """信用卡有"银行记账日",入 post_time。"""
    has_post = sum(1 for tx in parsed.raw_transactions if tx.post_time is not None)
    assert has_post >= len(parsed.raw_transactions) * 0.8, \
        "至少 80% 的交易应有银行记账日"


# === 边界 case 1:多币种 ===

def test_parse_foreign_currency_distinguishes_amounts(parsed):
    """若样本含外币(交易币 != CNY),amount 用交易币原值,amount_settled_cny 用结算币(CNY)。"""
    fx_txs = [tx for tx in parsed.raw_transactions if tx.currency != "CNY"]
    if fx_txs:  # 不强求,但有就必须正确
        for tx in fx_txs[:3]:
            # 交易币 USD/EUR 等,settled 必为 CNY
            assert tx.currency in ("USD", "EUR", "JPY", "HKD", "GBP", "AUD"), \
                f"unexpected currency: {tx.currency}"
            # 多币种交易,两个金额通常不等(汇率换算)
            assert tx.amount != tx.amount_settled_cny or tx.currency == "CNY"


def test_parse_cny_only_settled_equals_amount(parsed):
    """单币种 CNY 交易,settled == amount。"""
    cny_txs = [tx for tx in parsed.raw_transactions if tx.currency == "CNY"]
    for tx in cny_txs[:5]:
        assert tx.amount == tx.amount_settled_cny


# === 边界 case 2:银联入账还款 ===

def test_parse_unionpay_repayment_tagged_neutral(parsed):
    """描述含"银联入账"的行 → tx_kind=neutral(还款)。"""
    repayment_txs = [
        tx for tx in parsed.raw_transactions
        if "银联入账" in (tx.description_raw or "") or "银联入账" in (tx.merchant_raw or "")
    ]
    if repayment_txs:
        for tx in repayment_txs[:3]:
            assert tx.tx_kind == "neutral", \
                f"银联入账应为 neutral,实际 {tx.tx_kind}: {tx}"


# === 边界 case 3:财付通-/支付宝- 前缀 ===

def test_parse_channel_prefix_extracted_to_payment_method_raw(parsed):
    """描述以"财付通-"或"支付宝-"开头 → 前缀入 payment_method_raw,merchant_raw 剥前缀。"""
    prefix_txs = [
        tx for tx in parsed.raw_transactions
        if tx.payment_method_raw and any(
            tx.payment_method_raw.startswith(p) for p in ["财付通", "支付宝"]
        )
    ]
    if prefix_txs:
        for tx in prefix_txs[:3]:
            # merchant_raw 不应再以前缀开头
            assert not tx.merchant_raw.startswith("财付通-"), \
                f"merchant_raw 应已剥离财付通前缀: {tx.merchant_raw}"
            assert not tx.merchant_raw.startswith("支付宝-"), \
                f"merchant_raw 应已剥离支付宝前缀: {tx.merchant_raw}"
            # payment_method_raw 必含通道名
            assert any(tx.payment_method_raw.startswith(p) for p in ["财付通", "支付宝"])


def test_parse_metadata_counts(parsed):
    md = parsed.metadata
    assert md["imported_count"] == len(parsed.raw_transactions)


def test_parse_invalid_pdf_raises(parser: CcbCreditPdfParser):
    with pytest.raises(ValueError):
        parser.parse(b"not a pdf")
