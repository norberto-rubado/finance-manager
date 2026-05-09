"""statement_parser 包对外接口。

切片 C 的导入端点应只 import 本模块,不依赖具体解析器。
"""
from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
    StatementParser,
)
from app.services.statement_parser.normalize import normalize_merchant
from app.services.statement_parser.registry import (
    ALL_PARSERS,
    UnsupportedStatementError,
    route_and_parse,
)

__all__ = [
    # 数据类型
    "AccountHint",
    "ParseResult",
    "RawTransaction",
    "StatementParser",
    # 工具
    "normalize_merchant",
    # 路由
    "ALL_PARSERS",
    "UnsupportedStatementError",
    "route_and_parse",
]
