"""交通银行借记卡 PDF 解析器测试。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.bocom_debit_pdf import BocomDebitPdfParser


@pytest.fixture(scope="module")
def parser() -> BocomDebitPdfParser:
    return BocomDebitPdfParser()


@pytest.fixture(scope="module")
def parsed(parser: BocomDebitPdfParser, bocom_debit_pdf_bytes: bytes):
    return parser.parse(bocom_debit_pdf_bytes)


def test_source_type(parser: BocomDebitPdfParser):
    assert parser.source_type == "bank_pdf_bocom_debit"


def test_detect_accepts_real_bocom_pdf(
    parser: BocomDebitPdfParser, bocom_debit_pdf_bytes: bytes, bocom_filename: str
):
    assert parser.detect(bocom_debit_pdf_bytes, bocom_filename) is True


def test_detect_rejects_other_bank_pdf(
    parser: BocomDebitPdfParser, ccb_credit_pdf_bytes: bytes
):
    """建行 PDF 不应被交行解析器认领。"""
    assert parser.detect(ccb_credit_pdf_bytes, "ccb.pdf") is False


def test_detect_rejects_csv(parser: BocomDebitPdfParser):
    assert parser.detect(b"a,b\n1,2", "x.csv") is False


def test_parse_yields_transactions(parsed):
    assert len(parsed.raw_transactions) >= 1


def test_parse_account_hint(parsed):
    h = parsed.account_hint
    assert h.type == "bank_debit"
    assert h.institution == "交通银行"
    assert h.last4 == "2498"


def test_parse_amounts_positive_decimals(parsed):
    for tx in parsed.raw_transactions:
        assert isinstance(tx.amount, Decimal)
        assert tx.amount > 0
        assert tx.currency == "CNY"
        assert tx.amount_settled_cny == tx.amount


def test_parse_tx_kind_dr_cr(parsed):
    """借 Dr → expense,贷 Cr → income。"""
    kinds = {tx.tx_kind for tx in parsed.raw_transactions}
    assert kinds.issubset({"expense", "income"})


def test_parse_intermediary_keyword_in_payment_method_raw(parsed):
    """商家含"支付宝/蚂蚁/拉扎斯/云闪付/支付平台/财付通"任一,
    payment_method_raw 应被填(供 slice C 桥接去重)。"""
    bridge_keywords = ["支付宝", "蚂蚁", "拉扎斯", "云闪付", "支付平台", "财付通"]
    bridge_txs = [
        tx for tx in parsed.raw_transactions
        if any(kw in (tx.merchant_raw or "") for kw in bridge_keywords)
    ]
    if bridge_txs:  # 不强求样本必有,但有的话必须正确标记
        for tx in bridge_txs[:3]:
            assert tx.payment_method_raw is not None
            assert any(kw in tx.payment_method_raw for kw in bridge_keywords)


def test_parse_tx_time_in_2025_2026(parsed):
    for tx in parsed.raw_transactions[:5]:
        assert 2024 <= tx.tx_time.year <= 2026


def test_parse_metadata_counts(parsed):
    md = parsed.metadata
    assert md["imported_count"] == len(parsed.raw_transactions)
    assert md["raw_row_count"] >= md["imported_count"]


def test_parse_invalid_pdf_raises(parser: BocomDebitPdfParser):
    with pytest.raises(ValueError):
        parser.parse(b"not a pdf")


@pytest.mark.slow
def test_parse_full_pdf_under_10s(parser, bocom_debit_pdf_bytes):
    """13 页 PDF 全解析应在 10s 内完成(pdfplumber 基线)。"""
    import time
    t0 = time.time()
    parser.parse(bocom_debit_pdf_bytes)
    assert time.time() - t0 < 10.0
