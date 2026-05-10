"""Transaction schemas — spec § 4.1 + § 9.1 交易列表。"""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


TxKind = Literal["expense", "income", "neutral", "refund"]
SourceKind = Literal["bank", "alipay", "wechat", "conversation", "manual"]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    statement_import_id: int | None
    tx_kind: TxKind
    tx_time: datetime
    post_time: datetime | None
    amount: Decimal
    currency: str
    amount_settled_cny: Decimal
    merchant_raw: str | None
    merchant_normalized: str | None
    description_raw: str | None
    category_id: int | None
    classification_confidence: float | None
    source: SourceKind
    is_mirror: bool
    mirror_of_id: int | None


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class TransactionQuery(BaseModel):
    """GET /api/transactions query string 模型。"""
    date_from: datetime | None = None
    date_to: datetime | None = None
    account_id: int | None = None
    category_id: int | None = None
    kind: TxKind | None = None
    source: SourceKind | None = None
    is_mirror: bool | None = None
    keyword: str | None = None  # 模糊匹配 merchant_normalized
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class TransactionPatchIn(BaseModel):
    """PATCH /api/transactions/{id} 单条改类。"""
    category_id: int | None = None
    tx_kind: TxKind | None = None


class BulkUpdateByMerchantIn(BaseModel):
    """POST /api/transactions/bulk-update-by-merchant — spec § 8.1 同款,Web UI 也用。"""
    pattern: str = Field(..., min_length=1, max_length=255)
    match_kind: Literal["exact", "contains", "regex", "fuzzy"] = "contains"
    category_id: int
    also_add_rule: bool = True


class BulkUpdateResult(BaseModel):
    affected_count: int
    rule_id: int | None  # also_add_rule=True 时返回新建/复用的 rule_id


class TransactionCreateIn(BaseModel):
    """POST /api/transactions/manual — spec § 8.1 add_transaction 工具的 backend 等价。"""
    tx_time: datetime
    amount: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    currency: str = Field("CNY", min_length=3, max_length=8)
    merchant: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=512)
    account_id: int
    category_id: int | None = None
    tx_kind: TxKind = "expense"
