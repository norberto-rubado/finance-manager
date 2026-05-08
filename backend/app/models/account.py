"""Account 模型:银行卡/支付宝/微信/现金。"""
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # type ∈ bank_debit | bank_credit | alipay | wechat | cash
    institution: Mapped[str | None] = mapped_column(String(64))
    last4: Mapped[str | None] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(8), default="CNY", server_default="CNY")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
