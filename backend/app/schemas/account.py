"""Account schemas — spec § 4.1。"""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


AccountType = Literal["bank_debit", "bank_credit", "alipay", "wechat", "cash"]


class AccountCreate(BaseModel):
    name: str = Field(..., max_length=128)
    type: AccountType
    institution: str | None = Field(None, max_length=64)
    last4: str | None = Field(None, pattern=r"^\d{4}$")
    currency: str = "CNY"


class AccountUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    last4: str | None = Field(None, pattern=r"^\d{4}$")
    archived: bool | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: AccountType
    institution: str | None
    last4: str | None
    currency: str
    archived: bool


class AccountBalanceOut(AccountOut):
    """spec § 8.1 get_account_balances 工具的 backend 等价。继承 AccountOut + 余额字段。

    latest_balance 为流水推算(income - expense - refund),非银行真实余额。
    latest_balance_at = MAX(tx_time) of non-mirror tx,无交易时为 None。
    """
    latest_balance: Decimal
    latest_balance_at: datetime | None
