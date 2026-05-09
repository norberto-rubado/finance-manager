"""交通银行借记卡 PDF 解析器。

spec § 5.3.3:
- pdfplumber 抽表,6 列:交易日期 / 交易地点 / 交易方式 / 借贷状态 / 交易金额 / 余额
- 借贷状态:借 Dr → expense,贷 Cr → income
- 时间 YYYY-MM-DD
- 中转方关键词写 payment_method_raw,供切片 C 桥接去重
- 卡号末 4 位本切片保守固定 "2498"(用户实际卡号);从首页账号信息表提取

实现说明:
- extract_tables() 在本 PDF 完全可用:每页有 2 张表(账户信息表 + 交易明细表)
- 表头首行含 \n 分隔的中英文双语,取第一个 \n 前的中文部分作为列 key
- BOCOM_MARKERS 用英文字段("Trading Place"/"Trans Date")因为 pdfplumber
  从嵌入字体解出的字符是正确 unicode,但检测时也支持中文字符
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re

import pdfplumber

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
)


_BRIDGE_KEYWORDS = ["支付宝", "蚂蚁", "拉扎斯", "云闪付", "支付平台", "财付通"]

# 交行首页文本中出现的特征字符串(英文版本,兼容字体嵌入方式)
_BOCOM_MARKERS = [
    "BANK OF COMMUNICATIONS",
    "Trading Place",      # 交易地点列英文表头
    "Dc Flg",             # 借贷状态列英文表头
    "622262",             # 交通银行卡号前缀(保守兜底)
    "交通银行",
    "交易流水",
]

# 交易日期格式
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# 卡号末 4 位:从账号格式 "622262****2498" 或纯文字 "末 4 位 2498" 提取
_CARD_RE = re.compile(r"\*{4}(\d{4})")
_DEFAULT_LAST4 = "2498"


def _normalize_header(cell: str) -> str:
    """取表头单元格中文部分(首行,换行前)。"""
    return (cell or "").strip().split("\n")[0].strip()


def _parse_amount(s: str) -> Decimal:
    """解析金额字符串,去除逗号和货币符号。"""
    s = (s or "").strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not s:
        return Decimal("0")
    return Decimal(s)


def _detect_intermediary(merchant: str) -> str | None:
    """若商家名含中转方关键词,返回商家名作为 payment_method_raw 标记。"""
    if not merchant:
        return None
    if any(kw in merchant for kw in _BRIDGE_KEYWORDS):
        return merchant
    return None


def _extract_card_last4(info_table: list[list]) -> str:
    """从账户信息表里提取卡号末 4 位。"""
    for row in info_table:
        for cell in row:
            cell_str = str(cell or "")
            m = _CARD_RE.search(cell_str)
            if m:
                return m.group(1)
    return _DEFAULT_LAST4


class BocomDebitPdfParser:
    """交通银行借记卡 PDF 解析器。"""

    source_type = "bank_pdf_bocom_debit"

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        """嗅探:PDF magic + 首页文本含交行 marker。"""
        if not file_bytes.startswith(b"%PDF"):
            return False
        try:
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    return False
                first_text = pdf.pages[0].extract_text() or ""
                # 也检查首页表格内容(更可靠)
                first_tables = pdf.pages[0].extract_tables() or []
                tables_text = str(first_tables)
        except Exception:
            return False
        combined = first_text + tables_text
        return any(marker in combined for marker in _BOCOM_MARKERS)

    def parse(self, file_bytes: bytes) -> ParseResult:
        """解析交通银行借记卡 PDF,返回 ParseResult。"""
        if not file_bytes.startswith(b"%PDF"):
            raise ValueError("not a PDF file")

        try:
            pdf = pdfplumber.open(BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"bocom pdf open failed: {e}") from e

        try:
            last4 = _DEFAULT_LAST4
            raw_rows: list[dict] = []

            for page_idx, page in enumerate(pdf.pages):
                tables = page.extract_tables() or []
                for table in tables:
                    if not table:
                        continue

                    # 检查是否是账户信息表(含卡号),提取 last4
                    if page_idx == 0 and last4 == _DEFAULT_LAST4:
                        extracted = _extract_card_last4(table)
                        if extracted != _DEFAULT_LAST4:
                            last4 = extracted

                    # 检查是否是交易明细表:首行含"交易日期"或英文 "Trans Date"
                    header_row_idx = None
                    for i, row in enumerate(table):
                        row_str = "|".join(str(c or "") for c in row)
                        if "交易日期" in row_str or "Trans Date" in row_str:
                            header_row_idx = i
                            break
                    if header_row_idx is None:
                        continue

                    # 解析列索引
                    raw_header = table[header_row_idx]
                    headers = [_normalize_header(str(c or "")) for c in raw_header]

                    # 构建 col_map:中文列名 → 列下标
                    col_map: dict[str, int] = {}
                    for idx, h in enumerate(headers):
                        if h and h not in col_map:
                            col_map[h] = idx

                    # 数据行
                    for row in table[header_row_idx + 1:]:
                        if not row or not any(row):
                            continue
                        cells = [str(c or "").strip() for c in row]

                        # 首列必须是日期
                        date_col = col_map.get("交易日期", 0)
                        if date_col >= len(cells):
                            continue
                        date_cell = cells[date_col]
                        if not _DATE_RE.search(date_cell):
                            continue

                        d: dict[str, str] = {}
                        for col_name, col_idx in col_map.items():
                            d[col_name] = cells[col_idx] if col_idx < len(cells) else ""
                        raw_rows.append(d)

            # 解析每行为 RawTransaction
            txs: list[RawTransaction] = []
            all_times: list[datetime] = []

            for r in raw_rows:
                date_str = r.get("交易日期", "")
                m = _DATE_RE.search(date_str)
                if not m:
                    continue
                tx_time = datetime.strptime(m.group(0), "%Y-%m-%d")

                amt_str = r.get("交易金额", "") or r.get("金额", "") or "0"
                try:
                    amount = _parse_amount(amt_str)
                except InvalidOperation:
                    continue
                if amount <= 0:
                    continue

                # 借贷状态判断
                dc = r.get("借贷状态", "") or ""
                if "借" in dc or "Dr" in dc:
                    tx_kind = "expense"
                elif "贷" in dc or "Cr" in dc:
                    tx_kind = "income"
                else:
                    tx_kind = "neutral"

                merchant = r.get("交易地点", "").strip()
                desc = r.get("交易方式", "").strip() or None

                txs.append(
                    RawTransaction(
                        tx_time=tx_time,
                        post_time=None,
                        amount=amount,
                        currency="CNY",
                        amount_settled_cny=amount,
                        tx_kind=tx_kind,
                        merchant_raw=merchant,
                        counterparty_raw=None,
                        description_raw=desc,
                        external_tx_id=None,  # 交行 PDF 不暴露流水号
                        external_merchant_id=None,
                        payment_method_raw=_detect_intermediary(merchant),
                        raw_row=r,
                    )
                )
                all_times.append(tx_time)

            period_start = min(all_times) if all_times else datetime(1970, 1, 1)
            period_end = max(all_times) if all_times else datetime(1970, 1, 1)

            return ParseResult(
                raw_transactions=txs,
                account_hint=AccountHint(
                    type="bank_debit",
                    institution="交通银行",
                    last4=last4,
                ),
                period_start=period_start,
                period_end=period_end,
                metadata={
                    "raw_row_count": len(raw_rows),
                    "imported_count": len(txs),
                    "dropped_count": len(raw_rows) - len(txs),
                },
            )
        finally:
            pdf.close()
