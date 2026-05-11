"""Budget 服务 — spec § 4。"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget


def upsert_budget(
    db: Session,
    *,
    user_id: int,
    period_year: int,
    period_month: int,
    category_id: int | None,
    amount: Decimal,
    note: str | None,
) -> Budget:
    """按 (user, year, month, category_id) 主键 upsert。

    存在 → 更新 amount + note(不动 created_at);
    不存在 → 新建一条。
    """
    existing = db.execute(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.period_year == period_year,
            Budget.period_month == period_month,
            Budget.category_id.is_(None) if category_id is None
            else Budget.category_id == category_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.amount = amount
        existing.note = note
        db.flush()
        db.refresh(existing)  # 拉回 Numeric(12,2) 精度 + server_default 时间戳
        return existing

    new = Budget(
        user_id=user_id,
        period_year=period_year,
        period_month=period_month,
        category_id=category_id,
        amount=amount,
        note=note,
    )
    db.add(new)
    db.flush()
    db.refresh(new)  # 拉回 Numeric(12,2) 精度 + server_default 时间戳
    return new


def list_budgets(
    db: Session,
    *,
    user_id: int,
    period_year: int,
    period_month: int,
) -> list[Budget]:
    """列出某月所有预算(含总 + 各类别)。"""
    return list(db.execute(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.period_year == period_year,
            Budget.period_month == period_month,
        ).order_by(Budget.category_id.nullsfirst())
    ).scalars().all())


def copy_budgets_from(
    db: Session,
    *,
    user_id: int,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> tuple[list[Budget], bool]:
    """从 (from_year, from_month) 复制所有预算到 (to_year, to_month)。

    返回 (新建 list, 目标月是否已有数据)。
    目标月已有任何 budget 行 → 返回 ([], True),由 endpoint 转 409。
    """
    target_exists = db.execute(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.period_year == to_year,
            Budget.period_month == to_month,
        ).limit(1)
    ).scalar_one_or_none()
    if target_exists is not None:
        return [], True

    source = list(db.execute(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.period_year == from_year,
            Budget.period_month == from_month,
        )
    ).scalars().all())

    created: list[Budget] = []
    for src in source:
        new = Budget(
            user_id=user_id,
            period_year=to_year,
            period_month=to_month,
            category_id=src.category_id,
            amount=src.amount,
            note=src.note,
        )
        db.add(new)
        created.append(new)
    db.flush()
    for new in created:
        db.refresh(new)
    return created, False
