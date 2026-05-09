"""statement_parser 测试共享 fixture:文件路径常量 + 字节加载工具。"""
from pathlib import Path

import pytest


# 仓库根 / backend / tests / fixtures / statements
_FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "statements"


def _load(name: str) -> bytes:
    """加载 fixture 文件全部字节,文件不存在时给清晰错误。"""
    p = _FIXTURE_DIR / name
    if not p.exists():
        pytest.skip(f"fixture not found: {p} (run Task 6 to copy real samples)")
    return p.read_bytes()


@pytest.fixture(scope="module")
def alipay_csv_bytes() -> bytes:
    return _load("alipay_sample.csv")


@pytest.fixture(scope="module")
def wechat_xlsx_bytes() -> bytes:
    return _load("wechat_sample.xlsx")


@pytest.fixture(scope="module")
def bocom_debit_pdf_bytes() -> bytes:
    return _load("bocom_debit_sample.pdf")


@pytest.fixture(scope="module")
def ccb_credit_pdf_bytes() -> bytes:
    return _load("ccb_credit_sample.pdf")


@pytest.fixture(scope="module")
def alipay_filename() -> str:
    return "alipay_record_20260326_2219_1.csv"


@pytest.fixture(scope="module")
def wechat_filename() -> str:
    return "微信支付账单流水文件(20251226-20260326).xlsx"


@pytest.fixture(scope="module")
def bocom_filename() -> str:
    return "交通银行交易流水(申请时间2026年03月26日22时25分06秒).pdf"


@pytest.fixture(scope="module")
def ccb_filename() -> str:
    return "xykmx_20260508202125.pdf"
