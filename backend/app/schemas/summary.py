"""Summary schemas — spec § 8.1 get_summary。"""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel


GroupBy = Literal["category", "account", "merchant"]
Period = Literal["day", "week", "month", "year"]


class SummaryBreakdownItem(BaseModel):
    group_key: str   # category name / account name / merchant_normalized
    group_id: int | None
    amount: Decimal
    count: int


class SummaryOut(BaseModel):
    period: Period
    date_from: datetime
    date_to: datetime
    group_by: GroupBy
    total_expense: Decimal
    total_income: Decimal
    breakdown: list[SummaryBreakdownItem]
