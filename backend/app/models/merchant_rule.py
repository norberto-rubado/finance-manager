"""MerchantRule 模型:商家规则表。"""
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MerchantRule(Base, TimestampMixin):
    __tablename__ = "merchant_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # match_kind ∈ exact | contains | regex | fuzzy
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (
        # spec § 4.2 要求按优先级匹配,小数字先;DESC 不必,Postgres 规划器一样
        Index("ix_merchant_rules_user_priority", "user_id", "priority"),
    )
