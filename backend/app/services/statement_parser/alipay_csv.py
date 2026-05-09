"""支付宝个人账单 CSV 解析器。

spec § 5.3.1:
- 编码 GBK（gb18030 超集作 fallback）
- 跳前 4 行元信息,第 5 行表头,数据从第 6 行
- 16 列字段（标准支付宝导出；实际样本金额列为全角括号"金额（元）"）
- 仅保留"交易状态 = 交易成功"
- account_hint 固定为 (alipay, 支付宝, None)
- 不暴露外币不暴露底层卡

实际样本偏离 plan 的微调（2026-05-09 确认）:
  1. 金额列名为 "金额（元）"（全角括号 U+FF08/FF09），而非 "金额(元)"（ASCII）
  2. 表头行每格有大量空格填充（csv.DictReader strip 后一致）
  3. 末尾有 5 行统计行（"已收入:N笔..." 等），按交易号空/"-" 判断过滤
  4. 数据行字段值含前导/尾随空白，统一 .strip() 处理
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
import csv

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
)

# 元信息行特征字符串（用于 detect）
_META_MARKER = "支付宝交易记录明细查询"
# 即 "支付宝交易记录明细查询"


def _decode_bytes(data: bytes) -> str:
    """支付宝 CSV 主用 GBK，极少数生僻字回退 gb18030。"""
    for enc in ("gbk", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("gbk", data, 0, len(data), "cannot decode as GBK or GB18030")


def _parse_amount(s: str) -> Decimal:
    """金额列转 Decimal，容忍千分位逗号和货币符号。"""
    s = (s or "").strip().replace(",", "").replace("･", "").replace("\xa5", "")
    if not s:
        return Decimal("0")
    return Decimal(s)


def _parse_dt(s: str) -> datetime | None:
    """支付宝时间格式 'YYYY-MM-DD HH:MM:SS'。空串返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _infer_tx_kind(in_or_out: str) -> str:
    """收/支 列 → tx_kind。"""
    s = (in_or_out or "").strip()
    if s == "支出":   # "支出"
        return "expense"
    if s == "收入":   # "收入"
        return "income"
    # "/" 或空（转账/担保等）
    return "neutral"


def _find_amount_key(row: dict) -> str:
    """找金额列名（兼容全角/半角括号变体）。"""
    for k in row:
        if k.startswith("金额"):  # "金额"开头
            return k
    return ""


class AlipayCsvParser:
    source_type = "alipay_csv"

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        """嗅探：文件名 .csv 结尾 + GBK 解码后含"支付宝交易记录明细查询"特征。"""
        if not filename.lower().endswith(".csv"):
            return False
        try:
            head = file_bytes[:4096].decode("gbk", errors="ignore")
        except Exception:
            return False
        return _META_MARKER in head

    def parse(self, file_bytes: bytes) -> ParseResult:
        # --- 解码 ---
        try:
            text = _decode_bytes(file_bytes)
        except (UnicodeDecodeError, Exception) as e:
            raise ValueError(f"alipay csv decode failed: {e}") from e

        lines = text.splitlines()
        if len(lines) < 6:
            raise ValueError(
                "alipay csv too short (expect >=6 lines incl. 4 meta + header + 1 data)"
            )

        # 跳前 4 行元信息；第 5 行（index 4）是表头；数据从 index 5
        header_line = lines[4]
        data_lines = lines[5:]

        # --- 解析表头 ---
        # 支付宝表头每格含大量空格，拆分后统一 strip
        raw_header = [h.strip() for h in header_line.split(",")]

        # 简单校验关键列存在
        required = [
            "交易号",    # "交易号"
            "付款时间",  # "付款时间"
            "交易对方",  # "交易对方"
            "收/支",              # "收/支"
            "交易状态",  # "交易状态"
        ]
        missing = [k for k in required if k not in raw_header]
        if missing:
            raise ValueError(f"alipay csv missing columns: {missing}")

        if not any(k.startswith("金额") for k in raw_header):
            raise ValueError(
                f"alipay csv missing amount column (金额...) in header: {raw_header}"
            )

        # 用 csv.DictReader 解析（表头行 + 数据行重新组合）
        combined = "\n".join([",".join(raw_header)] + data_lines)
        reader = csv.DictReader(StringIO(combined), fieldnames=raw_header)
        next(reader)  # 跳过我们自己插入的伪表头行（fieldnames 已指定，第一行会被当作 header 消费掉）

        # --- 收集原始行，过滤 footer 注释行 ---
        raw_rows: list[dict] = []
        for row in reader:
            tx_id = (row.get("交易号") or "").strip()
            # footer 行：交易号为空或以 "-" 开头（分隔线），或以中文开头的统计行
            if not tx_id or tx_id.startswith("-"):
                continue
            # 过滤末尾统计行（"已收入:N笔..." 等，交易号列会是中文文字）
            # 真实交易号全是数字
            if not tx_id[:4].isdigit():
                continue
            raw_rows.append({k: (v or "").strip() for k, v in row.items()})

        # 仅保留"交易成功"
        success_rows = [
            r for r in raw_rows
            if r.get("交易状态") == "交易成功"
            # "交易状态" == "交易成功"
        ]

        # 找金额列名（全角括号"金额（元）"）
        amount_key = ""
        if success_rows:
            amount_key = _find_amount_key(success_rows[0])
        if not amount_key and raw_rows:
            amount_key = _find_amount_key(raw_rows[0])

        # --- 构建 RawTransaction 列表 ---
        txs: list[RawTransaction] = []
        all_times: list[datetime] = []

        for r in success_rows:
            try:
                amount_str = r.get(amount_key, "") if amount_key else ""
                amount = _parse_amount(amount_str)
            except InvalidOperation as e:
                raise ValueError(f"alipay csv bad amount in row {r}: {e}") from e

            if amount <= 0:
                # 金额为 0 的行（如退款手续费 0.00）跳过
                continue

            tx_time = _parse_dt(
                r.get("付款时间") or r.get("交易创建时间") or ""
                # "付款时间" or "交易创建时间"
            )
            if tx_time is None:
                continue
            all_times.append(tx_time)

            txs.append(RawTransaction(
                tx_time=tx_time,
                post_time=None,
                amount=amount,
                currency="CNY",
                amount_settled_cny=amount,
                tx_kind=_infer_tx_kind(r.get("收/支", "")),  # "收/支"
                merchant_raw=r.get("交易对方", ""),   # "交易对方"
                counterparty_raw=r.get("交易对方") or None,
                description_raw=r.get("商品名称") or None,  # "商品名称"
                external_tx_id=r.get("交易号") or None,         # "交易号"
                external_merchant_id=r.get("商家订单号") or None,  # "商家订单号"
                payment_method_raw=None,  # 支付宝 CSV 不暴露底层卡
                raw_row=r,
            ))

        period_start = min(all_times) if all_times else datetime(1970, 1, 1)
        period_end = max(all_times) if all_times else datetime(1970, 1, 1)

        return ParseResult(
            raw_transactions=txs,
            account_hint=AccountHint(
                type="alipay",
                institution="支付宝",  # "支付宝"
                last4=None,
            ),
            period_start=period_start,
            period_end=period_end,
            metadata={
                "raw_row_count": len(raw_rows),
                "imported_count": len(txs),
                "dropped_count": len(raw_rows) - len(txs),
            },
        )
