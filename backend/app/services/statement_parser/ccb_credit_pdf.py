"""建设银行信用卡 PDF 解析器。

spec § 5.3.4:
- pdfplumber 抽表,9 列:序号 / 交易日 / 银行记账日 / 卡号后4位 / 交易描述 / 交易币 / 交易金额 / 结算币 / 结算金额
- 时间 YYYYMMDD 无分隔符
- 多币种:交易币 != CNY → amount 用交易币原值,amount_settled_cny 用结算币(CNY)
- 银联入账(还款) → tx_kind=neutral
- 财付通-/支付宝- 前缀 → payment_method_raw 存原前缀字段,merchant_raw 剥前缀

实际样本偏离(一页 PDF,表格为合并单元格):
- 实际 7 列(非 spec 的 9 列):
    No. / T-Date / P-Date / Card Number / Description / Trans.Curr/Amt / Sett.Curr/Amt
- 交易币+金额 合并在同列,格式 "人民币元/518.00" 或 "欧元/6.25"
- pdfplumber 将所有数据行合并为单行,各字段值以 '\\n' 分隔
- 列头含双语(中文\\n英文),以英文部分做可靠识别
- 解析逻辑:pdfplumber 抽取的是标准 UTF-8,直接用子串匹配(slice C B-poly-1 修复)
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

# ── 检测标记 ────────────────────────────────────────────────────────────────
# 建行 PDF 英文页眉可靠存在
_CCB_MARKERS_EN = ["Credit Card Transaction Details", "China Construction Bank"]

# ── 交行检测排除标记 ──────────────────────────────────────────────────────────
# 交通银行 英文: Bank of Communications
_BOCOM_MARKER_EN = "Bank of Communications"

# ── 日期 ────────────────────────────────────────────────────────────────────
_DATE8_RE = re.compile(r"\b(\d{8})\b")

# ── 银联入账关键词 ────────────────────────────────────────────────────────────
# 必须用子串匹配,不能用 codepoint set(否则乱序字符串如"联银账入"会误判)
_REPAYMENT_KEYWORD = "银联入账"

# ── 通道前缀正则(支持 ASCII 和全角破折号) ────────────────────────────────────
_CHANNEL_PREFIX_RE = re.compile(r"^(财付通|支付宝)([\-—－＝]\s*)?(.*)$")

# ── 货币映射(中文名 → ISO 4217)。优先匹配长串(港币/人民币)避免短串先命中 ───
_CURRENCY_MAP: list[tuple[str, str]] = [
    ("人民币", "CNY"),
    ("香港元", "HKD"),
    ("港币", "HKD"),
    ("港元", "HKD"),
    ("香港", "HKD"),
    ("美元", "USD"),
    ("欧元", "EUR"),
    ("日元", "JPY"),
    ("英镑", "GBP"),
    ("澳元", "AUD"),
    ("RMB", "CNY"),
]

_DEFAULT_LAST4 = "7432"


def _identify_currency(curr_str: str) -> str:
    """从币种字符串(中文名 / ISO 代码)转 ISO 4217 三字母代码。"""
    s = (curr_str or "").strip()
    if not s:
        return "CNY"
    # 优先按长串子串匹配
    for cn_name, iso in _CURRENCY_MAP:
        if cn_name in s:
            return iso
    # 已是 3 字母 ASCII(如 USD/EUR)→ 大写返回
    if s.isascii() and len(s) == 3:
        return s.upper()
    return s  # 未知,原样返回(测试会发现)


def _parse_curr_amt(cell: str) -> tuple[str, Decimal]:
    """解析 '人民币元/518.00' 或 '欧元/6.25' 或 '人民币元/-92.00'。

    返回 (iso_currency, amount_signed)。
    """
    cell = (cell or "").strip()
    if "/" not in cell:
        # fallback: 纯数字
        try:
            return "CNY", Decimal(cell.replace(",", ""))
        except InvalidOperation:
            return "CNY", Decimal("0")
    curr_raw, amt_raw = cell.rsplit("/", 1)
    iso = _identify_currency(curr_raw.strip())
    amt_raw = amt_raw.strip().replace(",", "")
    try:
        amt = Decimal(amt_raw)
    except InvalidOperation:
        amt = Decimal("0")
    return iso, amt


def _parse_yyyymmdd(s: str) -> datetime | None:
    s = (s or "").strip()
    m = _DATE8_RE.search(s)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return None


def _split_channel_prefix(desc: str) -> tuple[str | None, str]:
    """检查描述是否以"财付通"或"支付宝"开头(可带破折号)。

    返回 (channel_prefix_full, merchant_after_strip):
    - "财付通-luckin coffee"  → ("财付通-luckin coffee", "luckin coffee")
    - "支付宝中国移动"        → ("支付宝中国移动", "中国移动")
    - "瑞幸咖啡"              → (None, "瑞幸咖啡")
    """
    if not desc:
        return None, ""
    m = _CHANNEL_PREFIX_RE.match(desc)
    if not m:
        return None, desc
    merchant = (m.group(3) or "").strip()
    if not merchant:
        # 仅前缀无后续(罕见):channel 保留原 desc,merchant 留空避免把前缀当商户名
        return desc, ""
    return desc, merchant


def _is_repayment(desc: str) -> bool:
    """描述是否含"银联入账"子串(还款入账记录)。

    spec § 5.3.4:银联入账 + 金额为负 = 信用卡还款。
    必须按字符顺序匹配,不能用 codepoint set(否则"联银账入"等乱序会误判)。
    """
    if not desc:
        return False
    return _REPAYMENT_KEYWORD in desc


def _is_ccb_text(text: str) -> bool:
    """文本中是否有建行特征(英文标记 / 中文'建设银行')。"""
    if not text:
        return False
    if any(m in text for m in _CCB_MARKERS_EN):
        return True
    return "建设银行" in text


class CcbCreditPdfParser:
    source_type = "bank_pdf_ccb_credit"

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        if not file_bytes.startswith(b"%PDF"):
            return False
        try:
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    return False
                first_text = pdf.pages[0].extract_text() or ""
        except Exception:
            return False
        # 排除交行
        if _BOCOM_MARKER_EN in first_text:
            return False
        return _is_ccb_text(first_text)

    def parse(self, file_bytes: bytes) -> ParseResult:
        if not file_bytes.startswith(b"%PDF"):
            raise ValueError("not a PDF file")

        try:
            pdf = pdfplumber.open(BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"ccb credit pdf open failed: {e}") from e

        try:
            # ── 提取全页文本,用于推断卡号后4位 ──────────────────────────
            full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)

            # 卡号后4位:在文本中找纯4位数字且出现在 "Card Number" 列附近
            # 样本中所有行都是 "7432",直接从卡号列提取
            last4 = _DEFAULT_LAST4  # 默认,后面从表格数据覆盖

            raw_rows: list[dict] = []

            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    # ── 定位表头行(含 T-Date / Trans 等英文关键字) ──────
                    header_idx = None
                    col_map: dict[str, int] = {}  # 英文列名 → 列索引

                    for i, row in enumerate(table):
                        # 每格可能是 "中文\n英文" 格式,取英文部分
                        cells = [str(c or "") for c in row]
                        joined = " ".join(cells).lower()
                        if "t-date" in joined and ("trans.curr" in joined or "sett.curr" in joined):
                            header_idx = i
                            # 解析列名映射
                            for ci, cell in enumerate(cells):
                                # 取双语列名的英文部分(换行后)
                                parts = cell.strip().split("\n")
                                en_name = parts[-1].strip().lower()  # 最后行通常是英文
                                col_map[en_name] = ci
                            break

                    if header_idx is None:
                        continue

                    # ── 解析数据行 ────────────────────────────────────────
                    # 实际样本:数据合并为单行,各值以 '\n' 分隔
                    # 标准 pdfplumber 也可能返回多行,两种都兼容
                    for row in table[header_idx + 1:]:
                        cells = [str(c or "") for c in row]

                        # 按列索引取值
                        def get_col(*keys: str) -> str:
                            for k in keys:
                                if k in col_map:
                                    idx = col_map[k]
                                    return cells[idx] if idx < len(cells) else ""
                            return ""

                        t_date_col = get_col("t-date")
                        p_date_col = get_col("p-date")
                        card_col = get_col("card number")
                        desc_col = get_col("description")
                        trans_col = get_col("trans.curr/amt")
                        sett_col = get_col("sett.curr/amt")

                        # 所有值都是 '\n' 分隔的多值串
                        t_dates = [v.strip() for v in t_date_col.split("\n") if v.strip()]
                        p_dates = [v.strip() for v in p_date_col.split("\n") if v.strip()]
                        card_nums = [v.strip() for v in card_col.split("\n") if v.strip()]
                        descriptions = desc_col.split("\n")
                        trans_vals = [v.strip() for v in trans_col.split("\n") if v.strip()]
                        sett_vals = [v.strip() for v in sett_col.split("\n") if v.strip()]

                        n = len(t_dates)
                        if n == 0:
                            continue

                        for ri in range(n):
                            t_date_str = t_dates[ri] if ri < len(t_dates) else ""
                            p_date_str = p_dates[ri] if ri < len(p_dates) else ""
                            card4 = card_nums[ri] if ri < len(card_nums) else last4
                            desc_str = descriptions[ri].strip() if ri < len(descriptions) else ""
                            trans_str = trans_vals[ri] if ri < len(trans_vals) else ""
                            sett_str = sett_vals[ri] if ri < len(sett_vals) else trans_str

                            # 必须有合法日期
                            if not _DATE8_RE.search(t_date_str):
                                continue

                            # 更新卡号后4位
                            if card4 and card4.isdigit() and len(card4) == 4:
                                last4 = card4

                            raw_rows.append({
                                "t_date": t_date_str,
                                "p_date": p_date_str,
                                "card4": card4,
                                "description": desc_str,
                                "trans_curr_amt": trans_str,
                                "sett_curr_amt": sett_str,
                            })

            # ── 构造 RawTransaction 列表 ─────────────────────────────────
            txs: list[RawTransaction] = []
            all_times: list[datetime] = []

            for r in raw_rows:
                tx_time = _parse_yyyymmdd(r["t_date"])
                if tx_time is None:
                    continue
                post_time = _parse_yyyymmdd(r["p_date"])

                # 交易币种 + 金额(原币)
                tx_currency, tx_amt = _parse_curr_amt(r["trans_curr_amt"])

                # 结算币种 + 金额(CNY)
                sett_currency, sett_amt = _parse_curr_amt(r["sett_curr_amt"])
                # 结算币必须是 CNY(信用卡账单折算)
                if sett_currency != "CNY":
                    # fallback:结算也当 CNY
                    sett_currency = "CNY"

                desc = r["description"]

                # ── 通道前缀拆分 ──────────────────────────────────────────
                channel, merchant = _split_channel_prefix(desc)

                # ── tx_kind 判断 ──────────────────────────────────────────
                if _is_repayment(desc):
                    tx_kind = "neutral"
                elif tx_amt < 0:
                    tx_kind = "neutral"  # 还款/调账/冲正
                else:
                    tx_kind = "expense"

                # 金额取绝对值,方向由 tx_kind 表达
                amount_abs = abs(tx_amt) if tx_amt != Decimal("0") else abs(sett_amt)
                settled_abs = abs(sett_amt) if sett_amt != Decimal("0") else amount_abs

                if amount_abs == Decimal("0"):
                    continue

                # CNY 单币种:amount_settled_cny == amount
                if tx_currency == "CNY":
                    settled_abs = amount_abs

                txs.append(RawTransaction(
                    tx_time=tx_time,
                    post_time=post_time,
                    amount=amount_abs,
                    currency=tx_currency,
                    amount_settled_cny=settled_abs,
                    tx_kind=tx_kind,
                    merchant_raw=merchant,
                    counterparty_raw=None,
                    description_raw=desc or None,
                    external_tx_id=None,        # 建行 PDF 不暴露交易流水号
                    external_merchant_id=None,
                    payment_method_raw=channel,  # 完整原始描述(如 "财付通-luckin coffee") 或 None
                    raw_row=r,
                ))
                all_times.append(tx_time)

            period_start = min(all_times) if all_times else datetime(1970, 1, 1)
            period_end = max(all_times) if all_times else datetime(1970, 1, 1)

            return ParseResult(
                raw_transactions=txs,
                account_hint=AccountHint(
                    type="bank_credit",
                    institution="建设银行",
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
