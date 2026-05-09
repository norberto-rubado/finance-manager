"""Account schemas — spec § 4.1。"""
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
