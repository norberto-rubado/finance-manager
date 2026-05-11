# 切片 B:Dashboard Snapshot API — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 4.4–4.7:`GET /api/dashboard/snapshot?year=&month=&client_date=`,一次返回 dashboard 上半区 + 下半区需要的所有数据(预算 / 已用 / 节奏 / 类别明细 / 6 月趋势 / 待办)。

**Architecture:** 在 `services/dashboard.py` 内封装 `compute_dashboard_snapshot()`,复用现有 `services/summary.compute_summary()`,组合 budgets + 三月均值 + 6 月趋势 + pending count。

**Tech Stack:** Python 3.11 / SQLAlchemy 2.0 / Pydantic v2 / pytest。

---

## 依赖

- 切片 A 完成(`budgets` 表 + CRUD API 可用)

## File Structure

**新建:**
```
backend/
  app/
    schemas/
      dashboard.py                 # DashboardSnapshot 及嵌套类型
    services/
      dashboard.py                 # compute_dashboard_snapshot + 子算法
    api/
      dashboard.py                 # APIRouter:GET /snapshot
  tests/
    services/
      test_dashboard.py
    api/
      test_dashboard.py
```

**修改:**
- `backend/app/schemas/__init__.py`:re-export DashboardSnapshot 等
- `backend/app/main.py`:include dashboard router

---

## Task B1:Snapshot schemas

**Files:**
- Create: `backend/app/schemas/dashboard.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1.1:创建 `backend/app/schemas/dashboard.py`**

```python
"""Dashboard snapshot schemas — spec § 4.5。"""
from decimal import Decimal

from pydantic import BaseModel


class SnapshotPeriod(BaseModel):
    year: int
    month: int
    day_of_month: int
    total_days: int
    is_current_month: bool


class SnapshotTotal(BaseModel):
    budget: Decimal | None   # null = 未设总预算
    spent: Decimal
    income: Decimal
    prev_month_spent: Decimal


class SnapshotPace(BaseModel):
    expected_ratio: float          # day_of_month / total_days
    actual_ratio: float | None     # spent / budget;无总预算 = None
    delta_pct: float | None        # (actual - expected) / expected * 100


class SnapshotCategory(BaseModel):
    category_id: int
    name: str
    icon: str | None
    color: str | None
    budget: Decimal | None
    spent: Decimal
    three_month_avg: Decimal
    note: str | None
    is_overspending: bool


class SnapshotTrendPoint(BaseModel):
    year: int
    month: int
    expense: Decimal
    income: Decimal


class SnapshotPending(BaseModel):
    uncategorized_count: int
    dedup_pending_count: int
    overspending_count: int


class DashboardSnapshot(BaseModel):
    period: SnapshotPeriod
    total: SnapshotTotal
    pace: SnapshotPace
    categories: list[SnapshotCategory]
    monthly_trend: list[SnapshotTrendPoint]
    pending: SnapshotPending
```

- [ ] **Step 1.2:更新 `backend/app/schemas/__init__.py`**

在文件中加 import:

```python
from app.schemas.dashboard import (
    DashboardSnapshot,
    SnapshotCategory,
    SnapshotPace,
    SnapshotPending,
    SnapshotPeriod,
    SnapshotTotal,
    SnapshotTrendPoint,
)
```

在 `__all__` 列表里加:

```python
    "DashboardSnapshot", "SnapshotPeriod", "SnapshotTotal", "SnapshotPace",
    "SnapshotCategory", "SnapshotTrendPoint", "SnapshotPending",
```

- [ ] **Step 1.3:验证 import**

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from app.schemas import DashboardSnapshot; print(DashboardSnapshot.model_fields.keys())"
```

期望输出包含 `period`、`total`、`pace`、`categories`、`monthly_trend`、`pending`。

- [ ] **Step 1.4:Commit**

```powershell
git add backend/app/schemas/dashboard.py backend/app/schemas/__init__.py
git commit -m "feat(schemas): add DashboardSnapshot and nested schemas"
```

---

## Task B2:Service 层主函数 + 子算法

**Files:**
- Create: `backend/app/services/dashboard.py`

- [ ] **Step 2.1:创建 `backend/app/services/dashboard.py`**

```python
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
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Budget, Category, DedupCandidate, Transaction
from app.services.summary import compute_summary


def _month_window(year: int, month: int) -> tuple[datetime, datetime]:
    """返回 [YYYY-MM-01 00:00, 下月1日 00:00)。"""
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
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
    if is_current_month:
        expected = day_of_month / total_days
    else:
        expected = 1.0

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
        spent_by_cat[item["group_id"]] = Decimal(str(item["amount"]))

    # ---- 上月 total expense ----
    prev_y, prev_m = _shift_month(query_year, query_month, -1)
    prev_start, prev_end = _month_window(prev_y, prev_m)
    prev_summary = compute_summary(
        db, user_id=user_id, date_from=prev_start, date_to=prev_end, group_by="category",
    )
    prev_total = Decimal(str(prev_summary["total_expense"]))

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
        spent = spent_by_cat.get(cat.id, Decimal("0"))
        avg = avg_by_cat.get(cat.id, Decimal("0"))
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
            "expense": Decimal(str(s["total_expense"])),
            "income": Decimal(str(s["total_income"])),
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
            "spent": Decimal(str(this_summary["total_expense"])),
            "income": Decimal(str(this_summary["total_income"])),
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
```

- [ ] **Step 2.2:验证 import + type check**

```powershell
.\.venv\Scripts\python.exe -c "from app.services.dashboard import compute_dashboard_snapshot; print('ok')"
.\.venv\Scripts\python.exe -m ruff check app/services/dashboard.py
```

期望:输出 `ok`,ruff 无报错。

- [ ] **Step 2.3:Commit**

```powershell
git add backend/app/services/dashboard.py
git commit -m "feat(services): compute_dashboard_snapshot main function"
```

---

## Task B3:Service 层 unit tests

**Files:**
- Create: `backend/tests/services/test_dashboard.py`

- [ ] **Step 3.1:创建测试**

```python
"""Dashboard service 测试 — 三月均值 / 节奏 / overspending。"""
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models import Account, Budget, Category, Transaction, User
from app.services.dashboard import (
    _compute_pace,
    _shift_month,
    compute_dashboard_snapshot,
    compute_three_month_avg,
)


@pytest.fixture
def u(db) -> User:
    user = User(username="u-dash", password_hash="x")
    db.add(user); db.flush()
    return user


@pytest.fixture
def acct(db, u) -> Account:
    a = Account(user_id=u.id, name="a-dash", type="bank_debit")
    db.add(a); db.flush()
    return a


@pytest.fixture
def cat_food(db, u) -> Category:
    c = Category(user_id=u.id, name="餐饮", kind="expense")
    db.add(c); db.flush()
    return c


def _add_tx(db, u, acct, cat, amount: str, when: datetime, kind: str = "expense") -> None:
    db.add(Transaction(
        user_id=u.id, account_id=acct.id, tx_kind=kind, tx_time=when,
        amount=Decimal(amount), amount_settled_cny=Decimal(amount),
        currency="CNY", source="manual", category_id=cat.id if cat else None,
    ))
    db.flush()


def test_shift_month():
    assert _shift_month(2026, 1, -1) == (2025, 12)
    assert _shift_month(2026, 12, 1) == (2027, 1)
    assert _shift_month(2026, 5, -3) == (2026, 2)


def test_compute_pace_current_month_no_budget():
    p = _compute_pace(is_current_month=True, day_of_month=15,
                      total_days=30, spent=Decimal("500"), budget=None)
    assert p["expected_ratio"] == 0.5
    assert p["actual_ratio"] is None
    assert p["delta_pct"] is None


def test_compute_pace_current_month_with_budget():
    p = _compute_pace(is_current_month=True, day_of_month=15,
                      total_days=30, spent=Decimal("750"),
                      budget=Decimal("1000"))
    assert p["expected_ratio"] == 0.5
    assert p["actual_ratio"] == 0.75
    # delta = (0.75 - 0.5) / 0.5 * 100 = 50
    assert p["delta_pct"] == 50.0


def test_compute_pace_past_month():
    p = _compute_pace(is_current_month=False, day_of_month=30,
                      total_days=30, spent=Decimal("1000"),
                      budget=Decimal("1000"))
    assert p["expected_ratio"] == 1.0
    assert p["actual_ratio"] == 1.0
    assert p["delta_pct"] == 0.0


def test_three_month_avg_no_data(db, u):
    assert compute_three_month_avg(
        db, user_id=u.id, query_year=2026, query_month=5,
    ) == {}


def test_three_month_avg_partial_data(db, u, acct, cat_food):
    # 4 月有数据,3 月、2 月没
    _add_tx(db, u, acct, cat_food, "100", datetime(2026, 4, 15))
    _add_tx(db, u, acct, cat_food, "200", datetime(2026, 4, 20))
    avg = compute_three_month_avg(
        db, user_id=u.id, query_year=2026, query_month=5,
    )
    # 总 300,只有 1 个月有数据,分母 1 → avg = 300
    assert avg[cat_food.id] == Decimal("300.00")


def test_three_month_avg_full_data(db, u, acct, cat_food):
    _add_tx(db, u, acct, cat_food, "300", datetime(2026, 4, 15))
    _add_tx(db, u, acct, cat_food, "600", datetime(2026, 3, 15))
    _add_tx(db, u, acct, cat_food, "300", datetime(2026, 2, 15))
    avg = compute_three_month_avg(
        db, user_id=u.id, query_year=2026, query_month=5,
    )
    # 总 1200 / 3 = 400
    assert avg[cat_food.id] == Decimal("400.00")


def test_snapshot_no_budget_no_data(db, u):
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    assert snap["total"]["budget"] is None
    assert snap["total"]["spent"] == Decimal("0")
    assert snap["pace"]["actual_ratio"] is None
    assert snap["period"]["is_current_month"] is True
    assert snap["period"]["day_of_month"] == 11
    assert snap["pending"]["uncategorized_count"] == 0
    assert snap["pending"]["overspending_count"] == 0


def test_snapshot_past_month_hides_pending(db, u):
    """非本月查询:pending 全 0,is_current_month=False。"""
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=4,
        client_date=date(2026, 5, 11),
    )
    assert snap["period"]["is_current_month"] is False
    assert snap["pace"]["expected_ratio"] == 1.0
    assert snap["pending"]["uncategorized_count"] == 0
    assert snap["pending"]["dedup_pending_count"] == 0


def test_snapshot_overspending(db, u, acct, cat_food):
    """本月 1500 支出,预算 1000 → is_overspending=True。"""
    _add_tx(db, u, acct, cat_food, "1500", datetime(2026, 5, 10))
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat_food.id, amount=Decimal("1000")))
    db.flush()
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    food_row = next(c for c in snap["categories"] if c["category_id"] == cat_food.id)
    assert food_row["is_overspending"] is True
    assert snap["pending"]["overspending_count"] == 1


def test_snapshot_month_trend_6_months(db, u):
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    trend = snap["monthly_trend"]
    assert len(trend) == 6
    # 升序:第一项是 2025 年 12 月,最后一项是 2026 年 5 月
    assert trend[0]["year"] == 2025 and trend[0]["month"] == 12
    assert trend[-1]["year"] == 2026 and trend[-1]["month"] == 5


def test_snapshot_prev_month_spent(db, u, acct, cat_food):
    _add_tx(db, u, acct, cat_food, "888", datetime(2026, 4, 15))
    snap = compute_dashboard_snapshot(
        db, user_id=u.id, query_year=2026, query_month=5,
        client_date=date(2026, 5, 11),
    )
    assert snap["total"]["prev_month_spent"] == Decimal("888.00")
```

- [ ] **Step 3.2:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_dashboard.py -v
```

期望:**11 个 test 全 PASS**。

- [ ] **Step 3.3:打印 P95 耗时**

为切片 B DoD 中的"P95 < 300ms"验证,跑一次带 1000 条 tx 的样本:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_dashboard.py -v --durations=10
```

观察 `test_snapshot_*` 的耗时。本地 1000 条 tx 应该 < 50ms。如果 > 200ms,启动**Step 3.4 的优化**;否则跳过。

- [ ] **Step 3.4:(条件触发)trend 优化 — 一条 SQL 跑 6 个月**

仅当 Step 3.3 显示慢时才做。把 `monthly_trend` 循环改为一条 GROUP BY 月份的 SQL:

```python
# 替换 monthly_trend 段
six_start, _ = _month_window(*_shift_month(query_year, query_month, -5))
_, six_end = _month_window(query_year, query_month)
rows = db.execute(
    select(
        func.extract("year", Transaction.tx_time).label("y"),
        func.extract("month", Transaction.tx_time).label("m"),
        Transaction.tx_kind,
        func.coalesce(func.sum(Transaction.amount_settled_cny), 0).label("amt"),
    )
    .where(
        Transaction.user_id == user_id,
        Transaction.is_mirror.is_(False),
        Transaction.tx_time >= six_start,
        Transaction.tx_time < six_end,
        Transaction.tx_kind.in_(["expense", "income"]),
    )
    .group_by("y", "m", Transaction.tx_kind)
).all()

# 用 dict 索引,填充 6 个月骨架
buckets: dict[tuple[int, int], dict[str, Decimal]] = {}
for i in range(5, -1, -1):
    y, m = _shift_month(query_year, query_month, -i)
    buckets[(y, m)] = {"expense": Decimal("0"), "income": Decimal("0")}
for y, m, kind, amt in rows:
    key = (int(y), int(m))
    if key in buckets:
        buckets[key][kind] = Decimal(str(amt))

trend = [
    {"year": y, "month": m, "expense": v["expense"], "income": v["income"]}
    for (y, m), v in sorted(buckets.items())
]
```

(优化后重新跑 Step 3.2 验证测试仍 PASS)

- [ ] **Step 3.5:Commit**

```powershell
git add backend/tests/services/test_dashboard.py
git commit -m "test(services): cover dashboard snapshot algorithm edge cases"
```

(如果 Step 3.4 做了,把 `app/services/dashboard.py` 也 add 进来)

---

## Task B4:API endpoint

**Files:**
- Create: `backend/app/api/dashboard.py`
- Modify: `backend/app/main.py`

- [ ] **Step 4.1:创建 `backend/app/api/dashboard.py`**

```python
"""Dashboard API — spec § 4.4。"""
from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep
from app.schemas import DashboardSnapshot
from app.services.dashboard import compute_dashboard_snapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/snapshot", response_model=DashboardSnapshot)
def snapshot_endpoint(
    user: CurrentUserDep, db: DbDep,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    client_date: date = Query(
        description="前端本地时区 YYYY-MM-DD,后端用它算 day_of_month / is_current_month",
    ),
) -> dict:
    return compute_dashboard_snapshot(
        db, user_id=user.id, query_year=year, query_month=month,
        client_date=client_date,
    )
```

- [ ] **Step 4.2:注册 router 到 `backend/app/main.py`**

打开 `backend/app/main.py`,在 import 部分(按字母序)加:

```python
from app.api import dashboard as dashboard_api
```

在 router include 列表中加:

```python
api_router.include_router(dashboard_api.router)
```

(位置放在 `budgets_api.router` 之后合理)

- [ ] **Step 4.3:验证 OpenAPI 文档生成**

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 &
# 等几秒
curl http://localhost:8000/openapi.json | python -m json.tool | findstr /C:"/dashboard/snapshot"
```

期望:输出包含 `"/api/dashboard/snapshot"`。

- [ ] **Step 4.4:Commit**

```powershell
git add backend/app/api/dashboard.py backend/app/main.py
git commit -m "feat(api): GET /dashboard/snapshot endpoint"
```

---

## Task B5:API e2e tests

**Files:**
- Create: `backend/tests/api/test_dashboard.py`

- [ ] **Step 5.1:创建测试**

```python
"""Dashboard API e2e — spec § 4.5 / overview 切片 B DoD 5 场景。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Account, Budget, Category, Transaction


@pytest.fixture
def cat_food(db, admin_user) -> Category:
    c = Category(user_id=admin_user.id, name="餐饮-dash", kind="expense")
    db.add(c); db.flush()
    return c


@pytest.fixture
def acct(db, admin_user) -> Account:
    a = Account(user_id=admin_user.id, name="a-dash", type="bank_debit")
    db.add(a); db.flush()
    return a


def _q(year: int, month: int, client_date: str) -> str:
    return f"/api/dashboard/snapshot?year={year}&month={month}&client_date={client_date}"


def test_snapshot_requires_login(client):
    r = client.get(_q(2026, 5, "2026-05-11"))
    assert r.status_code == 401


def test_snapshot_no_budget(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    assert r.status_code == 200
    body = r.json()
    assert body["total"]["budget"] is None
    assert body["pace"]["actual_ratio"] is None
    assert body["pending"]["overspending_count"] == 0


def test_snapshot_month_start_day_1(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-01"))
    body = r.json()
    assert body["period"]["day_of_month"] == 1
    # 5 月共 31 天
    assert body["period"]["total_days"] == 31
    assert abs(body["pace"]["expected_ratio"] - 1/31) < 0.001


def test_snapshot_prev_month_no_data(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    body = r.json()
    assert body["total"]["prev_month_spent"] == "0.00"


def test_snapshot_overspending(logged_in_client, db, admin_user, acct, cat_food):
    db.add(Transaction(
        user_id=admin_user.id, account_id=acct.id, tx_kind="expense",
        tx_time=datetime(2026, 5, 10),
        amount=Decimal("1500"), amount_settled_cny=Decimal("1500"),
        currency="CNY", source="manual", category_id=cat_food.id,
    ))
    db.add(Budget(user_id=admin_user.id, period_year=2026, period_month=5,
                  category_id=cat_food.id, amount=Decimal("1000")))
    db.flush()
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    body = r.json()
    assert body["pending"]["overspending_count"] == 1
    food = next(c for c in body["categories"] if c["category_id"] == cat_food.id)
    assert food["is_overspending"] is True


def test_snapshot_non_current_month(logged_in_client):
    r = logged_in_client.get(_q(2026, 4, "2026-05-11"))
    body = r.json()
    assert body["period"]["is_current_month"] is False
    assert body["pace"]["expected_ratio"] == 1.0
    assert body["pending"]["uncategorized_count"] == 0
    assert body["pending"]["dedup_pending_count"] == 0


def test_snapshot_invalid_query(logged_in_client):
    r = logged_in_client.get("/api/dashboard/snapshot?year=2026&month=5")
    assert r.status_code == 422   # 缺 client_date

    r = logged_in_client.get(_q(2026, 13, "2026-05-11"))
    assert r.status_code == 422   # month > 12


def test_snapshot_trend_has_6_months(logged_in_client):
    r = logged_in_client.get(_q(2026, 5, "2026-05-11"))
    trend = r.json()["monthly_trend"]
    assert len(trend) == 6
    # 升序
    assert trend[0]["month"] == 12 and trend[0]["year"] == 2025
    assert trend[-1]["month"] == 5 and trend[-1]["year"] == 2026
```

- [ ] **Step 5.2:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_dashboard.py -v
```

期望:**8 个 test 全 PASS**。

- [ ] **Step 5.3:Commit**

```powershell
git add backend/tests/api/test_dashboard.py
git commit -m "test(api): cover GET /dashboard/snapshot 5 DoD scenarios"
```

---

## Task B6:综合验证

- [ ] **Step 6.1:跑全部 dashboard + budget 相关测试**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/api/test_budgets.py tests/api/test_dashboard.py tests/services/test_budget_service.py tests/services/test_dashboard.py tests/models/test_budget.py -v
```

期望:全绿(切片 A 的 24 + 切片 B 的 19 = **43 个 test**)。

- [ ] **Step 6.2:跑 ruff**

```powershell
.\.venv\Scripts\python.exe -m ruff check app
```

期望:无报错。

- [ ] **Step 6.3:跑全部测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

期望:全绿。

- [ ] **Step 6.4:手动 smoke test snapshot 端点**

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```powershell
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"<pwd>"}' -c cookie.txt
curl "http://localhost:8000/api/dashboard/snapshot?year=2026&month=5&client_date=2026-05-11" -b cookie.txt
```

期望:返回完整 JSON,包含 `period`、`total`、`pace`、`categories`、`monthly_trend`、`pending` 6 个顶层 key。

---

## 切片 B 完成 DoD 复核

回到 [`2026-05-11-dashboard-overview.md`](2026-05-11-dashboard-overview.md) 切片 B 的 DoD 段:

- [x] `GET /api/dashboard/snapshot` 在 5 个场景下返回正确 JSON
- [x] P95 响应 < 300ms

切片 B 完成。下一步进入 [`2026-05-11-dashboard-slice-c-frontend-skeleton.md`](2026-05-11-dashboard-slice-c-frontend-skeleton.md)。
