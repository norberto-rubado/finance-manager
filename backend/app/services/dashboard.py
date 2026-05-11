"""Dashboard snapshot 服务 — spec § 4.6。

主入口 compute_dashboard_snapshot,组合:
- budgets 表(本月)
- compute_summary 本月分类支出
- compute_summary 上月总支出
- 三月均值(per category)
- 6 月趋势(每月一次 compute_summary 总额)
- pending count(未分类 + dedup pending + overspending)
"""
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Budget, Category, DedupCandidate, Transaction
from app.services.summary import compute_summary

_CENT = Decimal("0.01")


def _q2(value: Decimal) -> Decimal:
    """统一 Decimal 输出精度,确保 JSON 序列化为 "0.00" 而非 "0"。"""
    return Decimal(str(value)).quantize(_CENT)


def _month_window(year: int, month: int) -> tuple[datetime, datetime]:
    """返回 [YYYY-MM-01 00:00, 下月1日 00:00)。"""
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """(year, month) 加减 delta 月,返回新的 (year, month)。"""
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def compute_three_month_avg(
    db: Session,
    *,
    user_id: int,
    query_year: int,
    query_month: int,
) -> dict[int, Decimal]:
    """过去 3 个完整月(不含 query 月)按 category_id 的均值。

    返回 {category_id: avg_decimal}。
    不足 3 个月数据则用实际有数据的月数分母;0 个月数据返回 {}。
    """
    sums: dict[int, Decimal] = {}      # 累加每月总额
    months_with_data: dict[int, int] = {}  # 每个 category 出现的月份数

    for i in range(1, 4):
        y, m = _shift_month(query_year, query_month, -i)
        start, end = _month_window(y, m)
        rows = db.execute(
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount_settled_cny), 0).label("amt"),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.is_mirror.is_(False),
                Transaction.tx_kind == "expense",
                Transaction.tx_time >= start,
                Transaction.tx_time < end,
                Transaction.category_id.is_not(None),
            )
            .group_by(Transaction.category_id)
        ).all()
        for cat_id, amt in rows:
            sums[cat_id] = sums.get(cat_id, Decimal("0")) + Decimal(str(amt))
            months_with_data[cat_id] = months_with_data.get(cat_id, 0) + 1

    return {
        cid: (sums[cid] / months_with_data[cid]).quantize(Decimal("0.01"))
        for cid in sums
    }


def _compute_pace(
    *,
    is_current_month: bool,
    day_of_month: int,
    total_days: int,
    spent: Decimal,
    budget: Decimal | None,
) -> dict[str, float | None]:
    expected = day_of_month / total_days if is_current_month else 1.0

    if budget is None or budget == 0:
        return {"expected_ratio": round(expected, 4), "actual_ratio": None,
                "delta_pct": None}

    actual = float(spent) / float(budget)
    delta = None
    if expected > 0:
        delta = (actual - expected) / expected * 100
    return {
        "expected_ratio": round(expected, 4),
        "actual_ratio": round(actual, 4),
        "delta_pct": round(delta, 2) if delta is not None else None,
    }


def compute_dashboard_snapshot(
    db: Session,
    *,
    user_id: int,
    query_year: int,
    query_month: int,
    client_date: date,
) -> dict[str, Any]:
    """spec § 4.6 主函数。返回 dict 便于 endpoint 包成 DashboardSnapshot。"""
    # ---- period ----
    total_days = monthrange(query_year, query_month)[1]
    is_current = (client_date.year == query_year and client_date.month == query_month)
    day_of_month = client_date.day if is_current else total_days

    # ---- budgets 本月 ----
    budgets = list(db.execute(
        select(Budget).where(
            Budget.user_id == user_id,
            Budget.period_year == query_year,
            Budget.period_month == query_month,
        )
    ).scalars().all())
    total_budget: Decimal | None = None
    category_budgets: dict[int, tuple[Decimal, str | None]] = {}
    for b in budgets:
        if b.category_id is None:
            total_budget = b.amount
        else:
            category_budgets[b.category_id] = (b.amount, b.note)

    # ---- 本月 expense / income / 分类 breakdown ----
    start, end = _month_window(query_year, query_month)
    this_summary = compute_summary(
        db, user_id=user_id, date_from=start, date_to=end, group_by="category",
    )

    # 把 breakdown 按 category_id 索引
    spent_by_cat: dict[int | None, Decimal] = {}
    for item in this_summary["breakdown"]:
        spent_by_cat[item["group_id"]] = _q2(Decimal(str(item["amount"])))

    # ---- 上月 total expense ----
    prev_y, prev_m = _shift_month(query_year, query_month, -1)
    prev_start, prev_end = _month_window(prev_y, prev_m)
    prev_summary = compute_summary(
        db, user_id=user_id, date_from=prev_start, date_to=prev_end, group_by="category",
    )
    prev_total = _q2(prev_summary["total_expense"])

    # ---- pace ----
    pace = _compute_pace(
        is_current_month=is_current,
        day_of_month=day_of_month,
        total_days=total_days,
        spent=Decimal(str(this_summary["total_expense"])),
        budget=total_budget,
    )

    # ---- 三月均值(按 category)----
    avg_by_cat = compute_three_month_avg(
        db, user_id=user_id, query_year=query_year, query_month=query_month,
    )

    # ---- categories 列表(所有 expense 类别 + 有本月支出的)----
    all_cats = list(db.execute(
        select(Category).where(
            Category.user_id == user_id,
            Category.kind == "expense",
        )
    ).scalars().all())
    # 加入只在本月有支出但 category 已被删除的(很少见)的兜底:跳过(category_id 是软关联)
    categories_out: list[dict[str, Any]] = []
    for cat in all_cats:
        b_pair = category_budgets.get(cat.id)
        budget_amt = b_pair[0] if b_pair else None
        note = b_pair[1] if b_pair else None
        spent = spent_by_cat.get(cat.id, _q2(Decimal("0")))
        avg = avg_by_cat.get(cat.id, _q2(Decimal("0")))
        is_over = budget_amt is not None and spent > budget_amt
        categories_out.append({
            "category_id": cat.id,
            "name": cat.name,
            "icon": cat.icon,
            "color": cat.color,
            "budget": budget_amt,
            "spent": spent,
            "three_month_avg": avg,
            "note": note,
            "is_overspending": is_over,
        })

    # ---- 6 月趋势(含查询月,向前 6 个月,升序)----
    trend: list[dict[str, Any]] = []
    for i in range(5, -1, -1):
        y, m = _shift_month(query_year, query_month, -i)
        ms, me = _month_window(y, m)
        s = compute_summary(
            db, user_id=user_id, date_from=ms, date_to=me, group_by="category",
        )
        trend.append({
            "year": y,
            "month": m,
            "expense": _q2(s["total_expense"]),
            "income": _q2(s["total_income"]),
        })

    # ---- pending(仅本月有意义,非本月时清零)----
    if is_current:
        uncategorized = db.execute(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user_id,
                Transaction.is_mirror.is_(False),
                Transaction.category_id.is_(None),
            )
        ).scalar_one()
        dedup_pending = db.execute(
            select(func.count(DedupCandidate.id)).where(
                DedupCandidate.user_id == user_id,
                DedupCandidate.status == "pending",
            )
        ).scalar_one()
    else:
        uncategorized = 0
        dedup_pending = 0
    overspending = sum(1 for c in categories_out if c["is_overspending"])

    return {
        "period": {
            "year": query_year, "month": query_month,
            "day_of_month": day_of_month, "total_days": total_days,
            "is_current_month": is_current,
        },
        "total": {
            "budget": total_budget,
            "spent": _q2(this_summary["total_expense"]),
            "income": _q2(this_summary["total_income"]),
            "prev_month_spent": prev_total,
        },
        "pace": pace,
        "categories": categories_out,
        "monthly_trend": trend,
        "pending": {
            "uncategorized_count": int(uncategorized),
            "dedup_pending_count": int(dedup_pending),
            "overspending_count": overspending,
        },
    }
