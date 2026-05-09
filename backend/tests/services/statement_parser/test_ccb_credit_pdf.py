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


# ── helper 函数单元测试(覆盖 missing 行) ─────────────────────────────────────

from decimal import Decimal

from app.services.statement_parser.ccb_credit_pdf import (
    _identify_currency,
    _parse_curr_amt,
    _parse_yyyymmdd,
    _split_channel_prefix,
    _is_repayment,
)


class TestIdentifyCurrency:
    def test_cny_ren(self):
        # 人 U+4eba
        assert _identify_currency("人民币") == "CNY"

    def test_eur(self):
        # 欧 U+6b27
        assert _identify_currency("欧元") == "EUR"

    def test_hkd_gang(self):
        # 港 U+6e2f
        assert _identify_currency("港元") == "HKD"

    def test_hkd_xiang(self):
        # 香 U+9999
        assert _identify_currency("香港") == "HKD"

    def test_usd(self):
        # 美 U+7f8e
        assert _identify_currency("美元") == "USD"

    def test_jpy(self):
        # 日 U+65e5
        assert _identify_currency("日元") == "JPY"

    def test_gbp(self):
        # 英 U+82f1
        assert _identify_currency("英镑") == "GBP"

    def test_aud(self):
        # 澳 U+6fb3
        assert _identify_currency("澳元") == "AUD"

    def test_ascii_iso_code(self):
        assert _identify_currency("USD") == "USD"
        assert _identify_currency("eur") == "EUR"

    def test_unknown_passthrough(self):
        result = _identify_currency("ሴ噸")
        assert isinstance(result, str)


class TestParseCurrAmt:
    def test_cny_standard(self):
        iso, amt = _parse_curr_amt("人民币元/518.00")
        assert iso == "CNY"
        assert amt == Decimal("518.00")

    def test_eur_standard(self):
        iso, amt = _parse_curr_amt("欧元/6.25")
        assert iso == "EUR"
        assert amt == Decimal("6.25")

    def test_negative_amount(self):
        iso, amt = _parse_curr_amt("人民币元/-92.00")
        assert amt == Decimal("-92.00")

    def test_no_slash_numeric_fallback(self):
        # 没有 "/" 的纯数字应 fallback 为 CNY
        iso, amt = _parse_curr_amt("100.00")
        assert iso == "CNY"
        assert amt == Decimal("100.00")

    def test_no_slash_invalid_fallback(self):
        iso, amt = _parse_curr_amt("abc")
        assert iso == "CNY"
        assert amt == Decimal("0")

    def test_invalid_amount_part(self):
        iso, amt = _parse_curr_amt("人民币元/invalid")
        assert iso == "CNY"
        assert amt == Decimal("0")

    def test_empty_string(self):
        iso, amt = _parse_curr_amt("")
        assert iso == "CNY"


class TestParseYyyymmdd:
    def test_valid_date(self):
        from datetime import datetime
        result = _parse_yyyymmdd("20260326")
        assert result == datetime(2026, 3, 26)

    def test_no_match_returns_none(self):
        assert _parse_yyyymmdd("not a date") is None

    def test_empty_returns_none(self):
        assert _parse_yyyymmdd("") is None

    def test_date_in_text(self):
        from datetime import datetime
        result = _parse_yyyymmdd("Date: 20260101 end")
        assert result == datetime(2026, 1, 1)


class TestSplitChannelPrefix:
    def test_no_prefix(self):
        channel, merchant = _split_channel_prefix("McDonald's")
        assert channel is None
        assert merchant == "McDonald's"

    def test_empty_string(self):
        channel, merchant = _split_channel_prefix("")
        assert channel is None
        assert merchant == ""

    def test_caifutong_with_dash(self):
        desc = "财付通-SomeMerchant"
        channel, merchant = _split_channel_prefix(desc)
        assert channel == desc          # 完整 desc 作为 channel_prefix_full
        assert merchant == "SomeMerchant"

    def test_caifutong_without_dash(self):
        desc = "财付通SomeMerchant"
        channel, merchant = _split_channel_prefix(desc)
        assert channel == desc          # 完整 desc 作为 channel_prefix_full
        assert merchant == "SomeMerchant"

    def test_zhifubao_with_dash(self):
        desc = "支付宝-SomeMerchant"
        channel, merchant = _split_channel_prefix(desc)
        assert channel == desc          # 完整 desc 作为 channel_prefix_full
        assert merchant == "SomeMerchant"

    def test_zhifubao_without_dash(self):
        desc = "支付宝SomeMerchant"
        channel, merchant = _split_channel_prefix(desc)
        assert channel == desc          # 完整 desc 作为 channel_prefix_full
        assert merchant == "SomeMerchant"


class TestIsRepayment:
    def test_is_repayment_true(self):
        # 银联入账 = U+94f6 U+8054 U+5165 U+8d26
        desc = "银联入账"
        assert _is_repayment(desc) is True

    def test_is_repayment_false(self):
        assert _is_repayment("SomeMerchant") is False


# === B-poly-2 regression:_is_repayment 必须按子串顺序匹配 ===

from app.services.statement_parser.ccb_credit_pdf import _is_repayment  # noqa: E402,F811


def test_is_repayment_exact_match():
    """正常的银联入账描述应识别。"""
    assert _is_repayment("银联入账7432") is True
    assert _is_repayment("银联入账还款 7432****") is True


def test_is_repayment_rejects_scrambled_codepoints():
    """B-poly-2:仅含 4 字符但顺序错乱(set 解法会误中)→ 必须 False。"""
    assert _is_repayment("联银账入") is False
    assert _is_repayment("入账银联") is False
    assert _is_repayment("账入联银7432") is False


def test_is_repayment_rejects_partial_keywords():
    """仅含 4 字符中部分字符,真实商户名常见 → 必须 False。"""
    assert _is_repayment("联建银行账户激活") is False  # 含银/账,但不组成"银联入账"
    assert _is_repayment("入金账户充值") is False        # 含入/账
    assert _is_repayment("瑞幸咖啡") is False
    assert _is_repayment("") is False


def test_is_repayment_substring_match_in_longer_desc():
    """嵌入更长描述里的"银联入账"应识别(模拟真实 PDF 多空格场景)。"""
    assert _is_repayment("12月银联入账还款记录") is True
    assert _is_repayment("XX 银联入账 YY") is True
