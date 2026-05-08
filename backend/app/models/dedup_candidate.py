"""DedupCandidate 模型:待审核去重对。"""
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DedupCandidate(Base, TimestampMixin):
    __tablename__ = "dedup_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    primary_tx_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE")
    )
    mirror_tx_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE")
    )
    match_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # match_kind ∈ strong | bridge | conversation
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    # status ∈ pending | confirmed | rejected
    reasoning: Mapped[dict | None] = mapped_column(JSONB)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_dedup_user_status", "user_id", "status"),
    )
