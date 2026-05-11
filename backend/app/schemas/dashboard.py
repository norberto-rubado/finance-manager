"""Dashboard snapshot schemas — spec § 4.5。"""
from decimal import Decimal

from pydantic import BaseModel


class SnapshotPeriod(BaseModel):
    year: int
    month: int
    day_of_month: int
    total_days: int
    is_current_month: bool


class SnapshotTotal(BaseModel):
    budget: Decimal | None   # null = 未设总预算
    spent: Decimal
    income: Decimal
    prev_month_spent: Decimal


class SnapshotPace(BaseModel):
    expected_ratio: float          # day_of_month / total_days
    actual_ratio: float | None     # spent / budget;budget=None 或 budget=0 时 = None
    delta_pct: float | None        # (actual - expected) / expected * 100


class SnapshotCategory(BaseModel):
    category_id: int
    name: str
    icon: str | None
    color: str | None
    budget: Decimal | None
    spent: Decimal
    three_month_avg: Decimal
    note: str | None
    is_overspending: bool


class SnapshotTrendPoint(BaseModel):
    year: int
    month: int
    expense: Decimal
    income: Decimal


class SnapshotPending(BaseModel):
    uncategorized_count: int
    dedup_pending_count: int
    overspending_count: int


class DashboardSnapshot(BaseModel):
    period: SnapshotPeriod
    total: SnapshotTotal
    pace: SnapshotPace
    categories: list[SnapshotCategory]
    monthly_trend: list[SnapshotTrendPoint]
    pending: SnapshotPending
