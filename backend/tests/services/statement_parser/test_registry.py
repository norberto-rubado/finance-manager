"""router/registry 测试:detect 路由 + 每种文件归对应 parser。"""
import pytest

from app.services.statement_parser.registry import (
    ALL_PARSERS,
    UnsupportedStatementError,
    route_and_parse,
)


def test_all_parsers_registered():
    """4 个解析器全部注册。"""
    types = {p.source_type for p in ALL_PARSERS}
    assert types == {
        "alipay_csv",
        "wechat_xlsx",
        "bank_pdf_bocom_debit",
        "bank_pdf_ccb_credit",
    }


def test_route_alipay(alipay_csv_bytes, alipay_filename):
    result = route_and_parse(alipay_csv_bytes, alipay_filename)
    assert result.account_hint.type == "alipay"


def test_route_wechat(wechat_xlsx_bytes, wechat_filename):
    result = route_and_parse(wechat_xlsx_bytes, wechat_filename)
    assert result.account_hint.type == "wechat"


def test_route_bocom(bocom_debit_pdf_bytes, bocom_filename):
    result = route_and_parse(bocom_debit_pdf_bytes, bocom_filename)
    assert result.account_hint.type == "bank_debit"
    assert result.account_hint.institution == "交通银行"


def test_route_ccb(ccb_credit_pdf_bytes, ccb_filename):
    result = route_and_parse(ccb_credit_pdf_bytes, ccb_filename)
    assert result.account_hint.type == "bank_credit"
    assert result.account_hint.institution == "建设银行"


def test_route_unknown_raises():
    with pytest.raises(UnsupportedStatementError):
        route_and_parse(b"random bytes that nobody recognizes", "x.txt")


def test_route_dispatches_to_correct_parser_when_two_could_match(
    bocom_debit_pdf_bytes, ccb_credit_pdf_bytes
):
    """两个 PDF 解析器只能命中各自的 marker,不能交叉。"""
    bocom_result = route_and_parse(bocom_debit_pdf_bytes, "x.pdf")
    assert bocom_result.account_hint.institution == "交通银行"
    ccb_result = route_and_parse(ccb_credit_pdf_bytes, "x.pdf")
    assert ccb_result.account_hint.institution == "建设银行"
