"""Budget 模型:月度预算。category_id NULL = 总预算。"""
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )  # NULL = 该月总预算
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        Index("ix_budgets_user_period", "user_id", "period_year", "period_month"),
        # 两个 partial unique index:Postgres NULL 兼容性 —
        # category_id 非空 → 同月同 category 只能一条
        # category_id 为空 → 同月总预算只能一条
        Index(
            "uq_budget_period_category",
            "user_id", "period_year", "period_month", "category_id",
            unique=True,
            postgresql_where=text("category_id IS NOT NULL"),
        ),
        Index(
            "uq_budget_period_total",
            "user_id", "period_year", "period_month",
            unique=True,
            postgresql_where=text("category_id IS NULL"),
        ),
    )
