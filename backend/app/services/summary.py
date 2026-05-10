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


def compute_account_balances(db: Session, *, user_id: int) -> list[dict[str, Any]]:
    """spec § 8.1 get_account_balances 算法,纯函数。

    余额 = SUM(income.amount_settled_cny)
         - SUM(expense.amount_settled_cny)
         - SUM(refund.amount_settled_cny)
    其中 is_mirror=True 的全部排除;neutral(信用卡还款等)不计余额但计 latest_balance_at。

    返回每个 account(无论是否有交易)一条:
        {account_id, latest_balance: Decimal, latest_balance_at: datetime | None}
    """
    # 全 user 的 accounts
    accounts = db.execute(
        select(Account.id).where(Account.user_id == user_id)
    ).scalars().all()

    base = (
        Transaction.user_id == user_id,
        Transaction.is_mirror.is_(False),
    )

    # 按 account_id + tx_kind 聚合
    rows = db.execute(
        select(
            Transaction.account_id,
            Transaction.tx_kind,
            func.coalesce(func.sum(Transaction.amount_settled_cny), 0).label("amt"),
        )
        .where(*base)
        .group_by(Transaction.account_id, Transaction.tx_kind)
    ).all()

    # 单独查 latest tx_time(neutral 也算)
    last_rows = db.execute(
        select(
            Transaction.account_id,
            func.max(Transaction.tx_time).label("last_at"),
        )
        .where(*base)
        .group_by(Transaction.account_id)
    ).all()
    last_by_acc = {acc_id: last_at for acc_id, last_at in last_rows}

    # 折叠 income / expense / refund per account
    income: dict[int, Decimal] = {}
    expense: dict[int, Decimal] = {}
    refund: dict[int, Decimal] = {}
    for acc_id, kind, amt in rows:
        amt_dec = Decimal(str(amt))
        if kind == "income":
            income[acc_id] = income.get(acc_id, Decimal("0")) + amt_dec
        elif kind == "expense":
            expense[acc_id] = expense.get(acc_id, Decimal("0")) + amt_dec
        elif kind == "refund":
            refund[acc_id] = refund.get(acc_id, Decimal("0")) + amt_dec
        # neutral: 跳过(只用于 last_at)

    # 每个 account 都返回(无交易时 balance=0, last_at=None)
    out: list[dict[str, Any]] = []
    for acc_id in accounts:
        bal = (income.get(acc_id, Decimal("0"))
               - expense.get(acc_id, Decimal("0"))
               - refund.get(acc_id, Decimal("0")))
        out.append({
            "account_id": acc_id,
            "latest_balance": bal.quantize(Decimal("0.01")),
            "latest_balance_at": last_by_acc.get(acc_id),
        })
    return out
