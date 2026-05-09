"""解析器自动路由。

spec § 5.1 step 3:导入端点接到 file_bytes 后,需要选对解析器。
本模块按 detect() 顺序匹配第一个 hit 的解析器。
"""
from app.services.statement_parser.alipay_csv import AlipayCsvParser
from app.services.statement_parser.base import ParseResult, StatementParser
from app.services.statement_parser.bocom_debit_pdf import BocomDebitPdfParser
from app.services.statement_parser.ccb_credit_pdf import CcbCreditPdfParser
from app.services.statement_parser.wechat_xlsx import WechatXlsxParser


# 顺序无关(detect 互斥),但便于调试:CSV → xlsx → 银行 PDF
ALL_PARSERS: list[StatementParser] = [
    AlipayCsvParser(),
    WechatXlsxParser(),
    BocomDebitPdfParser(),
    CcbCreditPdfParser(),
]


class UnsupportedStatementError(ValueError):
    """4 个解析器都不认 → 抛此异常,切片 C 的端点转 HTTP 400。"""


def route_and_parse(file_bytes: bytes, filename: str) -> ParseResult:
    """按 detect 顺序找第一个能处理的解析器,parse 后返回。

    无解析器认领 → UnsupportedStatementError(用户友好的错误,带上文件名)。
    """
    for parser in ALL_PARSERS:
        try:
            if parser.detect(file_bytes, filename):
                return parser.parse(file_bytes)
        except Exception:
            # detect 不应抛错,但万一抛了,继续试下一个
            continue
    raise UnsupportedStatementError(
        f"no parser matched filename={filename!r} (head bytes: {file_bytes[:32]!r})"
    )
