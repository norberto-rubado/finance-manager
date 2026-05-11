"""Budget schemas — spec § 4.3。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BudgetIn(BaseModel):
    """PUT /budgets 的 body。"""
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    category_id: int | None = None  # None = 总预算
    amount: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)


class BudgetOut(BudgetIn):
    """GET / PUT / DELETE 返回的形态。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class BudgetCopyIn(BaseModel):
    """POST /budgets/copy-from 的 body。"""
    from_year: int = Field(ge=2000, le=2100)
    from_month: int = Field(ge=1, le=12)
    to_year: int = Field(ge=2000, le=2100)
    to_month: int = Field(ge=1, le=12)
