"""Summary 服务 — spec § 8.1 算法,纳函数。"""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction


def compute_summary(
    db: Session,
    *,
    user_id: int,
    date_from: datetime,
    date_to: datetime,
    group_by: str,  # category | account | merchant
) -> dict[str, Any]:
    """spec § 8.1。返回 dict 便于 schemas 端组装 SummaryOut。"""
    base_where = [
        Transaction.user_id == user_id,
        Transaction.is_mirror.is_(False),
        Transaction.tx_time >= date_from,
        Transaction.tx_time <= date_to,
    ]

    # 总额（expense / income）
    expense_total = db.execute(
        select(func.coalesce(func.sum(Transaction.amount_settled_cny), 0))
        .where(*base_where, Transaction.tx_kind == "expense")
    ).scalar_one()
    income_total = db.execute(
        select(func.coalesce(func.sum(Transaction.amount_settled_cny), 0))
        .where(*base_where, Transaction.tx_kind == "income")
    ).scalar_one()

    # 仅在 expense 维度 breakdown（spec § 8.1 默认看支出大头）
    breakdown_where = base_where + [Transaction.tx_kind == "expense"]

    if group_by == "category":
        rows = db.execute(
            select(
                Transaction.category_id,
                Category.name,
                func.sum(Transaction.amount_settled_cny).label("amt"),
                func.count(Transaction.id).label("cnt"),
            )
            .outerjoin(Category, Category.id == Transaction.category_id)
            .where(*breakdown_where)
            .group_by(Transaction.category_id, Category.name)
            .order_by(func.sum(Transaction.amount_settled_cny).desc())
        ).all()
        breakdown = [
            {"group_key": (name or "未分类"), "group_id": cat_id,
             "amount": amt, "count": cnt}
            for cat_id, name, amt, cnt in rows
        ]
    elif group_by == "account":
        rows = db.execute(
            select(
                Account.id, Account.name,
                func.sum(Transaction.amount_settled_cny).label("amt"),
                func.count(Transaction.id).label("cnt"),
            )
            .join(Account, Account.id == Transaction.account_id)
            .where(*breakdown_where)
            .group_by(Account.id, Account.name)
            .order_by(func.sum(Transaction.amount_settled_cny).desc())
        ).all()
        breakdown = [
            {"group_key": name, "group_id": aid,
             "amount": amt, "count": cnt}
            for aid, name, amt, cnt in rows
        ]
    elif group_by == "merchant":
        rows = db.execute(
            select(
                Transaction.merchant_normalized,
                func.sum(Transaction.amount_settled_cny).label("amt"),
                func.count(Transaction.id).label("cnt"),
            )
            .where(*breakdown_where)
            .group_by(Transaction.merchant_normalized)
            .order_by(func.sum(Transaction.amount_settled_cny).desc())
        ).all()
        breakdown = [
            {"group_key": (m or "(空商户名)"), "group_id": None,
             "amount": amt, "count": cnt}
            for m, amt, cnt in rows
        ]
    else:
        raise ValueError(f"unknown group_by: {group_by!r}")

    return {
        "total_expense": Decimal(str(expense_total)),
        "total_income": Decimal(str(income_total)),
        "breakdown": breakdown,
    }
