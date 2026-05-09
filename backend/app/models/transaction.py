"""Transaction 模型:MVP 核心表。"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    statement_import_id: Mapped[int | None] = mapped_column(
        ForeignKey("statement_imports.id", ondelete="SET NULL")
    )

    tx_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # tx_kind ∈ expense | income | neutral | refund
    tx_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    post_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", server_default="CNY")
    amount_settled_cny: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    merchant_raw: Mapped[str | None] = mapped_column(String(255))
    merchant_normalized: Mapped[str | None] = mapped_column(String(255))
    counterparty_raw: Mapped[str | None] = mapped_column(String(255))
    description_raw: Mapped[str | None] = mapped_column(String(512))

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # source ∈ bank | alipay | wechat | conversation | manual
    external_tx_id: Mapped[str | None] = mapped_column(String(128))
    external_merchant_id: Mapped[str | None] = mapped_column(String(128))
    payment_method_raw: Mapped[str | None] = mapped_column(String(128))

    is_mirror: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    mirror_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )

    source_unique_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        # spec § 4.2:主查询路径(交易列表按时间倒序翻页),DESC 让 PG 直接走 index scan
        Index("ix_transactions_user_tx_time", "user_id", text("tx_time DESC")),
        Index("ix_transactions_user_account_time", "user_id", "account_id", "tx_time"),
        Index("ix_transactions_user_merchant_norm", "user_id", "merchant_normalized"),
    )
