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
- 中文字符在 Python 内部存储为正确 UTF-8(U+xxxx),但 Windows 终端显示乱码
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
# 建行 Unicode 关键字: "建设银行" U+5efa U+8bbe U+94f6 U+884c
_CCB_MARKER_ZH_CP = (0x5efa, 0x8bbe, 0x94f6, 0x884c)  # 建 设 银 行(简体)

# ── 交行检测排除标记 ──────────────────────────────────────────────────────────
# 交通银行 英文: Bank of Communications
_BOCOM_MARKER_EN = "Bank of Communications"

# ── 日期 ────────────────────────────────────────────────────────────────────
_DATE8_RE = re.compile(r"\b(\d{8})\b")

# ── 银联入账 codepoints (银联入账 = U+94f6 U+8054 U+5165 U+8d26) ─────────
_YINLIAN_CP = (0x94f6, 0x8054)          # 银联 (前两字即可定位)
_RUZHANG_CP = (0x5165, 0x8d26)          # 入账

# ── 通道前缀 ─────────────────────────────────────────────────────────────────
# 财付通 U+8d22 U+4ed8 U+901a
_CAIFUTONG_CP = (0x8d22, 0x4ed8, 0x901a)
# 支付宝 U+652f U+4ed8 U+5b9d
_ZHIFUBAO_CP = (0x652f, 0x4ed8, 0x5b9d)

# ── 货币映射(中文名 → ISO 4217),以首个码点集合识别 ────────────────────────
# 人民币元: 人 U+4eba  民 U+6c11  币 U+5e01
# 欧元:     欧 U+6b27  元 U+5143
# 港元/香港元: 港 U+6e2f 或 香 U+9999 + 港 U+6e2f
# 美元:     美 U+7f8e  元 U+5143
# 日元:     日 U+65e5  元 U+5143
# 英镑:     英 U+82f1
# 澳元:     澳 U+6fb3

_DEFAULT_LAST4 = "7432"


def _has_codepoints(s: str, cps: tuple) -> bool:
    """字符串 s 是否包含所有码点(顺序不要求连续)。"""
    cp_set = {ord(c) for c in s}
    return all(cp in cp_set for cp in cps)


def _starts_with_codepoints(s: str, cps: tuple) -> bool:
    """字符串 s 的开头 len(cps) 个字符是否依次等于 cps 中各码点。"""
    if len(s) < len(cps):
        return False
    return all(ord(s[i]) == cps[i] for i in range(len(cps)))


def _identify_currency(curr_str: str) -> str:
    """从中文币种名称转为 ISO 4217 代码。"""
    cp_set = {ord(c) for c in curr_str}
    # 人民币: 包含 人(4eba) 或 民(6c11)
    if 0x4eba in cp_set or 0x6c11 in cp_set:
        return "CNY"
    # 欧元: 欧(6b27)
    if 0x6b27 in cp_set:
        return "EUR"
    # 港元/香港元: 港(6e2f) 或 香(9999)
    if 0x6e2f in cp_set or 0x9999 in cp_set:
        return "HKD"
    # 美元: 美(7f8e)
    if 0x7f8e in cp_set:
        return "USD"
    # 日元: 日(65e5)
    if 0x65e5 in cp_set:
        return "JPY"
    # 英镑: 英(82f1)
    if 0x82f1 in cp_set:
        return "GBP"
    # 澳元: 澳(6fb3)
    if 0x6fb3 in cp_set:
        return "AUD"
    # 已是 ASCII ISO 代码(如 USD/EUR)
    if curr_str.isascii() and len(curr_str) == 3:
        return curr_str.upper()
    return curr_str  # 未知,原样返回


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
    """检查描述是否以财付通- 或 支付宝- 开头。

    返回 (channel_label, merchant_after_strip)。
    - channel_label: 原始通道名(含破折号及后续内容作为完整存证)
    - merchant_after_strip: 剥去前缀后的商户名
    """
    if not desc:
        return None, ""

    # 财付通 (U+8d22 U+4ed8 U+901a) + 分隔符 + 商户
    if _starts_with_codepoints(desc, _CAIFUTONG_CP):
        # 找到分隔符(- 或 — 或其他)
        rest = desc[3:]  # 跳过财付通
        if rest and rest[0] in "-—－＝":
            merchant = rest[1:]
            channel = "财付通"
        else:
            merchant = rest
            channel = "财付通"
        return channel, merchant

    # 支付宝 (U+652f U+4ed8 U+5b9d) + 分隔符 + 商户
    if _starts_with_codepoints(desc, _ZHIFUBAO_CP):
        rest = desc[3:]  # 跳过支付宝
        if rest and rest[0] in "-—－＝":
            merchant = rest[1:]
            channel = "支付宝"
        else:
            merchant = rest
            channel = "支付宝"
        return channel, merchant

    return None, desc


def _is_repayment(desc: str) -> bool:
    """描述是否含银联入账(还款)。"""
    return _has_codepoints(desc, _YINLIAN_CP + _RUZHANG_CP)


def _is_ccb_text(text: str) -> bool:
    """文字中是否有建行特征。"""
    # 英文标记最可靠
    if any(m in text for m in _CCB_MARKERS_EN):
        return True
    # 中文建设银行
    if _has_codepoints(text, _CCB_MARKER_ZH_CP):
        return True
    return False


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
                    payment_method_raw=channel,  # "财付通" 或 "支付宝" 或 None
                    raw_row=r,
                ))
                all_times.append(tx_time)

            period_start = min(all_times) if all_times else datetime(1970, 1, 1)
            period_end = max(all_times) if all_times else datetime(1970, 1, 1)

            return ParseResult(
                raw_transactions=txs,
                account_hint=AccountHint(
                    type="bank_credit",
                    institution="建设银行",  # U+5efa U+8bbe U+94f6 U+884c
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
