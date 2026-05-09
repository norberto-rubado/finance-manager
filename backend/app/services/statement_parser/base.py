"""解析器统一数据模型 + Protocol。

spec 引用:§ 5.2 解析器接口(统一抽象)
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass
class AccountHint:
    """解析器从账单内容推断到的账户标识。

    导入时 (slice C) 用 (user_id, institution, last4) 在 accounts 表查/建。
    支付宝/微信 last4=None,固定走单一全局账户。
    """
    type: str          # bank_debit | bank_credit | alipay | wechat | cash
    institution: str   # "支付宝" | "微信支付" | "交通银行" | "建设银行" 等
    last4: str | None  # 银行卡末 4 位;支付宝/微信为 None


@dataclass
class RawTransaction:
    """解析器输出的单条交易,字段对齐 spec § 5.2 + 补 external_merchant_id。

    所有金额必须用 Decimal,数字始终为正(方向靠 tx_kind);
    raw_row 保留原始字段,审计追溯用。
    """
    tx_time: datetime
    post_time: datetime | None
    amount: Decimal
    currency: str               # 'CNY' | 'USD' | 'EUR' 等 ISO 4217
    amount_settled_cny: Decimal # 多币种交易折算 CNY,单币种交易 == amount
    tx_kind: str                # expense | income | neutral | refund
    merchant_raw: str           # 原始商户名(给 normalize 用)
    counterparty_raw: str | None
    description_raw: str | None
    external_tx_id: str | None      # 同源防重导入用(支付宝交易号/微信交易单号等)
    external_merchant_id: str | None # 支付宝"商家订单号"等
    payment_method_raw: str | None  # 微信"支付方式"列原文,跨源去重锚定用
    raw_row: dict = field(default_factory=dict)  # 原始行,JSONB 进 transactions.raw_payload


@dataclass
class ParseResult:
    """解析器对一份账单文件的完整产出。"""
    raw_transactions: list[RawTransaction]
    account_hint: AccountHint
    period_start: datetime
    period_end: datetime
    metadata: dict = field(default_factory=dict)
    # metadata 常见 key:row_count_in_header / expense_total / income_total / dropped_count
    # 用于切片 C 导入完成后的"对账校验"(汇总能否对得上账单页眉)


class StatementParser(Protocol):
    """所有解析器的统一接口(structural typing,实现类无需显式继承)。

    spec § 5.2: detect 用于自动路由,parse 抽出全部交易。
    """
    source_type: str  # alipay_csv | wechat_xlsx | bank_pdf_bocom_debit | bank_pdf_ccb_credit

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        """嗅探 file_bytes 是否归本解析器处理。可看文件头/扩展名/特征字符串。"""
        ...

    def parse(self, file_bytes: bytes) -> ParseResult:
        """解析整个文件。失败时 raise ValueError(message)。"""
        ...
