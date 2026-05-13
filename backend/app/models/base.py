"""SQLAlchemy 2 declarative base + 通用时间戳 mixin。"""
from datetime import datetime
from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# 命名约定:自动生成索引/约束名,Alembic 比较时稳定
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """所有业务表都带 created_at / updated_at。

    限制(MVP 范围接受):
    - `created_at` 用 `server_default=func.now()` -> Postgres 在 INSERT 时填充,
      任何路径(ORM / 裸 SQL / COPY)都生效。
    - `updated_at` 的 `onupdate=func.now()` 仅在 **SQLAlchemy ORM 触发的 UPDATE**
      时生效 —— ORM 会在 SQL 中加 `updated_at = now()` 子句。
    - 绕过 ORM 的路径 **不会** 自动更新 `updated_at`,常见场景:
        * `session.execute(text("UPDATE ... WHERE ..."))`
        * `pg_insert(...).on_conflict_do_update(...)`(ON CONFLICT 走 PG 层)
        * 通过 psql / DBeaver 手动 UPDATE
      此时如要更新 `updated_at`,必须在裸 SQL 中显式 `SET updated_at = now()`,
      或在 PG 加 `BEFORE UPDATE` trigger(MVP 范围内不引入触发器)。
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
