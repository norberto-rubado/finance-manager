# 切片 A:budgets 表 + CRUD API — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 4.1–4.4:新增 `budgets` 表 + 5 个 REST 端点(`GET / PUT / DELETE /budgets`、`POST /budgets/copy-from`),为后续切片(snapshot API + 前端)提供数据底座。

**Architecture:** 跟现有 `categories` / `accounts` 完全一致的分层:`models/` → `schemas/` → `services/` → `api/`。唯一约束用两个 partial unique index 解决 Postgres NULL 兼容性问题。

**Tech Stack:** Python 3.11 / SQLAlchemy 2.0 / Pydantic v2 / Alembic 1.14 / Postgres 16 / pytest。

---

## File Structure(本切片涉及)

**新建:**
```
backend/
  app/
    models/
      budget.py                    # Budget ORM 模型
    schemas/
      budget.py                    # BudgetIn / BudgetOut / BudgetCopyIn
    services/
      budget.py                    # upsert_budget / copy_budgets_from
    api/
      budgets.py                   # APIRouter:5 个端点
  alembic/
    versions/
      0003_budgets_table.py        # migration(含两个 partial unique index)
  tests/
    models/
      __init__.py
      test_budget.py
    api/
      test_budgets.py
    services/
      test_budget_service.py
```

**修改:**
- `backend/app/models/__init__.py`:re-export `Budget`
- `backend/app/schemas/__init__.py`:re-export `BudgetIn / BudgetOut / BudgetCopyIn`
- `backend/app/main.py`:`api_router.include_router(budgets_api.router)`

---

## Task A1:Budget ORM 模型

**Files:**
- Create: `backend/app/models/budget.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1.1:创建 `backend/app/models/budget.py`**

```python
"""Budget 模型:月度预算。category_id NULL = 总预算。"""
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )  # NULL = 该月总预算
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        Index("ix_budgets_user_period", "user_id", "period_year", "period_month"),
        # 唯一约束:用两个 partial unique index 在 migration 中创建
        # (SQLAlchemy 的 UniqueConstraint 不支持 partial,只能写在 migration 里)
    )
```

- [ ] **Step 1.2:把 Budget 加入 `backend/app/models/__init__.py`**

打开文件,在 import 列表末尾加 `from app.models.budget import Budget`,`__all__` 列表加 `"Budget"`。完整对照:

```python
"""模型集中 re-export,供 Alembic env.py 一次性导入。"""
from app.models.base import Base, TimestampMixin
from app.models.user import User
from app.models.account import Account
from app.models.category import Category
from app.models.merchant_rule import MerchantRule
from app.models.statement_import import StatementImport
from app.models.transaction import Transaction
from app.models.dedup_candidate import DedupCandidate
from app.models.api_token import ApiToken
from app.models.budget import Budget

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "Account",
    "Category",
    "MerchantRule",
    "StatementImport",
    "Transaction",
    "DedupCandidate",
    "ApiToken",
    "Budget",
]
```

- [ ] **Step 1.3:验证 import 不报错**

```powershell
cd backend
.\.venv\Scripts\python.exe -c "from app.models import Budget; print(Budget.__tablename__)"
```

期望输出:`budgets`

- [ ] **Step 1.4:Commit**

```powershell
git add backend/app/models/budget.py backend/app/models/__init__.py
git commit -m "feat(models): add Budget model for monthly budgets"
```

---

## Task A2:Alembic migration(含两个 partial unique index)

**Files:**
- Create: `backend/alembic/versions/0003_budgets_table.py`

- [ ] **Step 2.1:让 Alembic 自动生成 migration**

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "add budgets table"
```

期望:在 `alembic/versions/` 生成一个新文件,文件名形如 `<hash>_add_budgets_table.py`。把它**重命名**为 `0003_budgets_table.py`,文件头部 `revision = "0003"`,`down_revision = "0002"`(查上一个 migration 文件验证 revision 号是 `"0002"`)。

- [ ] **Step 2.2:编辑生成的 migration,补两个 partial unique index**

打开 `0003_budgets_table.py`,在 `op.create_table('budgets', ...)` 之后,`op.create_index('ix_budgets_user_period', ...)` 之后,加:

```python
    # category_id NOT NULL 时的唯一:同月同 category 只能一条
    op.create_index(
        "uq_budget_period_category",
        "budgets",
        ["user_id", "period_year", "period_month", "category_id"],
        unique=True,
        postgresql_where=sa.text("category_id IS NOT NULL"),
    )
    # category_id IS NULL 时的唯一:同月总预算只能一条
    op.create_index(
        "uq_budget_period_total",
        "budgets",
        ["user_id", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("category_id IS NULL"),
    )
```

对应在 `downgrade()` 顶部加:

```python
    op.drop_index("uq_budget_period_total", table_name="budgets")
    op.drop_index("uq_budget_period_category", table_name="budgets")
```

(`drop_index('ix_budgets_user_period', ...)` 和 `drop_table('budgets')` 应该已经由 autogenerate 填好,顺序:先 drop indexes 再 drop table)

- [ ] **Step 2.3:跑 upgrade**

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

期望输出:`Running upgrade 0002 -> 0003, add budgets table`,无报错。

- [ ] **Step 2.4:在 psql 验证两个 partial index 存在**

```powershell
docker-compose --profile dev exec db psql -U finance -d finance_db -c "\d budgets"
```

期望输出在 "Indexes:" 章节里看到:
```
"uq_budget_period_category" UNIQUE, btree (user_id, period_year, period_month, category_id) WHERE category_id IS NOT NULL
"uq_budget_period_total" UNIQUE, btree (user_id, period_year, period_month) WHERE category_id IS NULL
"ix_budgets_user_period" btree (user_id, period_year, period_month)
```

(数据库用户名可能不是 `finance`,看 `.env` 里 `DATABASE_URL`,实际命令对应)

- [ ] **Step 2.5:验证 downgrade 不报错**

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
```

期望:`downgrade` 不报错,`upgrade` 再次跑通。

- [ ] **Step 2.6:Commit**

```powershell
git add backend/alembic/versions/0003_budgets_table.py
git commit -m "feat(db): migration for budgets table with partial unique indexes"
```

---

## Task A3:Pydantic schemas

**Files:**
- Create: `backend/app/schemas/budget.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 3.1:创建 `backend/app/schemas/budget.py`**

```python
"""Budget schemas — spec § 4.3。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BudgetIn(BaseModel):
    """PUT /budgets 的 body。"""
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    category_id: int | None = None  # None = 总预算
    amount: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)


class BudgetOut(BudgetIn):
    """GET / PUT / DELETE 返回的形态。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class BudgetCopyIn(BaseModel):
    """POST /budgets/copy-from 的 body。"""
    from_year: int = Field(ge=2000, le=2100)
    from_month: int = Field(ge=1, le=12)
    to_year: int = Field(ge=2000, le=2100)
    to_month: int = Field(ge=1, le=12)
```

- [ ] **Step 3.2:更新 `backend/app/schemas/__init__.py`**

在文件中加 import + `__all__`(参照现有 imports 的排序风格):

```python
# 在 imports 区,按字母序加:
from app.schemas.budget import BudgetCopyIn, BudgetIn, BudgetOut

# 在 __all__ 列表里加:
    "BudgetIn", "BudgetOut", "BudgetCopyIn",
```

- [ ] **Step 3.3:验证 import**

```powershell
.\.venv\Scripts\python.exe -c "from app.schemas import BudgetIn, BudgetOut, BudgetCopyIn; print(BudgetIn.model_fields.keys())"
```

期望输出包含 `'period_year', 'period_month', 'category_id', 'amount', 'note'`。

- [ ] **Step 3.4:Commit**

```powershell
git add backend/app/schemas/budget.py backend/app/schemas/__init__.py
git commit -m "feat(schemas): add BudgetIn/BudgetOut/BudgetCopyIn"
```

---

## Task A4:Service 层 — upsert + copy

**Files:**
- Create: `backend/app/services/budget.py`
- Create: `backend/tests/services/test_budget_service.py`

- [ ] **Step 4.1:创建 `backend/app/services/budget.py`**

```python
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
    return created, False
```

- [ ] **Step 4.2:创建 `backend/tests/services/test_budget_service.py`**

```python
"""Budget service 单元测试 — upsert + copy 边界。"""
from decimal import Decimal

import pytest

from app.models import Budget, Category, User
from app.services.budget import copy_budgets_from, list_budgets, upsert_budget


@pytest.fixture
def admin(db) -> User:
    user = User(username="admin-svc", password_hash="x")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def cat_food(db, admin) -> Category:
    cat = Category(user_id=admin.id, name="餐饮-test", kind="expense")
    db.add(cat)
    db.flush()
    return cat


def test_upsert_creates_new(db, admin):
    b = upsert_budget(
        db, user_id=admin.id, period_year=2026, period_month=5,
        category_id=None, amount=Decimal("3000"), note="总预算",
    )
    assert b.id is not None
    assert b.amount == Decimal("3000.00")


def test_upsert_updates_existing(db, admin):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note="old")
    b2 = upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                       category_id=None, amount=Decimal("3500"), note="new")
    rows = list_budgets(db, user_id=admin.id, period_year=2026, period_month=5)
    assert len(rows) == 1
    assert rows[0].amount == Decimal("3500.00")
    assert rows[0].note == "new"


def test_upsert_total_and_category_independent(db, admin, cat_food):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note=None)
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=cat_food.id, amount=Decimal("1500"), note=None)
    rows = list_budgets(db, user_id=admin.id, period_year=2026, period_month=5)
    assert len(rows) == 2


def test_copy_from_happy(db, admin, cat_food):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=4,
                  category_id=None, amount=Decimal("3000"), note=None)
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=4,
                  category_id=cat_food.id, amount=Decimal("1500"), note="餐饮")
    created, conflict = copy_budgets_from(
        db, user_id=admin.id, from_year=2026, from_month=4,
        to_year=2026, to_month=5,
    )
    assert conflict is False
    assert len(created) == 2
    rows_may = list_budgets(db, user_id=admin.id, period_year=2026, period_month=5)
    assert len(rows_may) == 2


def test_copy_from_empty_source(db, admin):
    """上月没数据 → 返回空 list,不报错。"""
    created, conflict = copy_budgets_from(
        db, user_id=admin.id, from_year=2026, from_month=3,
        to_year=2026, to_month=5,
    )
    assert conflict is False
    assert created == []


def test_copy_from_target_already_has_data(db, admin, cat_food):
    upsert_budget(db, user_id=admin.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note=None)
    created, conflict = copy_budgets_from(
        db, user_id=admin.id, from_year=2026, from_month=4,
        to_year=2026, to_month=5,
    )
    assert conflict is True
    assert created == []
```

- [ ] **Step 4.3:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_budget_service.py -v
```

期望:6 个 test 全 PASS。

如果测试找不到 `db` fixture,确认 `backend/tests/conftest.py` 顶层有 `db` fixture 定义(项目 slice A 已有)。

- [ ] **Step 4.4:Commit**

```powershell
git add backend/app/services/budget.py backend/tests/services/test_budget_service.py
git commit -m "feat(services): add budget upsert/list/copy helpers"
```

---

## Task A5:模型唯一约束测试

**Files:**
- Create: `backend/tests/models/__init__.py`
- Create: `backend/tests/models/test_budget.py`

- [ ] **Step 5.1:创建 `backend/tests/models/__init__.py`**

(空文件即可,占位让 pytest 发现)

```powershell
ni backend/tests/models/__init__.py
```

- [ ] **Step 5.2:创建 `backend/tests/models/test_budget.py`**

```python
"""Budget 模型 — 两个 partial unique index 验证。"""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Budget, User


@pytest.fixture
def u(db) -> User:
    user = User(username="u-budget", password_hash="x")
    db.add(user)
    db.flush()
    return user


def test_unique_total_budget_per_month(db, u):
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000")))
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("4000")))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_unique_category_budget_per_month(db, u):
    from app.models import Category
    cat = Category(user_id=u.id, name="c1", kind="expense")
    db.add(cat)
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat.id, amount=Decimal("500")))
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat.id, amount=Decimal("600")))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_different_months_are_independent(db, u):
    db.add(Budget(user_id=u.id, period_year=2026, period_month=4,
                  category_id=None, amount=Decimal("3000")))
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3500")))
    db.flush()  # 不应报错


def test_total_and_category_can_coexist(db, u):
    from app.models import Category
    cat = Category(user_id=u.id, name="c2", kind="expense")
    db.add(cat)
    db.flush()
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000")))
    db.add(Budget(user_id=u.id, period_year=2026, period_month=5,
                  category_id=cat.id, amount=Decimal("1500")))
    db.flush()  # 不应报错(NULL 和非 NULL 走的是不同的 partial index)
```

- [ ] **Step 5.3:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/models/test_budget.py -v
```

期望:4 个 test 全 PASS。

如果 `IntegrityError` 在 sqlite 测试库下跑出不同行为(sqlite 不支持 partial index),检查 `tests/conftest.py` 应该是用真 Postgres(slice A 已经选 Postgres 作 test db)。

- [ ] **Step 5.4:Commit**

```powershell
git add backend/tests/models/
git commit -m "test(models): verify Budget partial unique constraints"
```

---

## Task A6:API endpoint — `GET /budgets`

**Files:**
- Create: `backend/app/api/budgets.py`
- Create: `backend/tests/api/test_budgets.py`

- [ ] **Step 6.1:创建 `backend/app/api/budgets.py`**

```python
"""Budgets API — spec § 4.4。"""
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUserDep, DbDep
from app.schemas import BudgetCopyIn, BudgetIn, BudgetOut
from app.services.budget import (
    copy_budgets_from,
    list_budgets,
    upsert_budget,
)
from app.models import Budget

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut])
def list_endpoint(
    user: CurrentUserDep, db: DbDep,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
) -> list[Budget]:
    return list_budgets(db, user_id=user.id, period_year=year, period_month=month)
```

- [ ] **Step 6.2:注册 router 到 `backend/app/main.py`**

打开 `backend/app/main.py`,在 imports 部分加 `from app.api import budgets as budgets_api`(按字母序),然后在 `api_router.include_router(...)` 列表里加 `api_router.include_router(budgets_api.router)`(放在 `summary_api.router` 后面合理)。

- [ ] **Step 6.3:创建 `backend/tests/api/test_budgets.py`(GET 部分)**

```python
"""Budgets API e2e。"""
from decimal import Decimal

from app.models import Budget, Category


def test_list_empty(logged_in_client):
    r = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_budgets(logged_in_client, db, admin_user):
    db.add(Budget(user_id=admin_user.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("3000"), note="总"))
    db.flush()
    r = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["amount"] == "3000.00"
    assert items[0]["note"] == "总"
    assert items[0]["category_id"] is None


def test_list_requires_login(client):
    r = client.get("/api/budgets?year=2026&month=5")
    assert r.status_code == 401


def test_list_validates_query(logged_in_client):
    r = logged_in_client.get("/api/budgets?year=2026&month=13")
    assert r.status_code == 422
```

- [ ] **Step 6.4:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_budgets.py -v
```

期望:4 个 test 全 PASS。

- [ ] **Step 6.5:Commit**

```powershell
git add backend/app/api/budgets.py backend/app/main.py backend/tests/api/test_budgets.py
git commit -m "feat(api): GET /budgets endpoint"
```

---

## Task A7:API endpoint — `PUT /budgets`(upsert)

**Files:**
- Modify: `backend/app/api/budgets.py`
- Modify: `backend/tests/api/test_budgets.py`

- [ ] **Step 7.1:在 `backend/app/api/budgets.py` 末尾加 PUT 端点**

```python
@router.put("", response_model=BudgetOut)
def upsert_endpoint(
    user: CurrentUserDep, db: DbDep,
    body: BudgetIn,
) -> Budget:
    return upsert_budget(
        db,
        user_id=user.id,
        period_year=body.period_year,
        period_month=body.period_month,
        category_id=body.category_id,
        amount=body.amount,
        note=body.note,
    )
```

- [ ] **Step 7.2:在 `backend/tests/api/test_budgets.py` 末尾追加 PUT 测试**

```python
def test_put_creates_new(logged_in_client):
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "3000", "note": "总预算",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount"] == "3000.00"
    assert body["note"] == "总预算"
    assert body["id"] is not None


def test_put_updates_existing(logged_in_client):
    logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "3000", "note": "old",
    })
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "3500", "note": "new",
    })
    assert r.status_code == 200
    assert r.json()["amount"] == "3500.00"
    assert r.json()["note"] == "new"
    # 列表只有一条
    rl = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert len(rl.json()) == 1


def test_put_with_category(logged_in_client, db, admin_user):
    cat = Category(user_id=admin_user.id, name="餐饮-api", kind="expense")
    db.add(cat); db.flush()
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": cat.id, "amount": "1500", "note": None,
    })
    assert r.status_code == 200
    assert r.json()["category_id"] == cat.id


def test_put_validates_amount_negative(logged_in_client):
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "-100", "note": None,
    })
    assert r.status_code == 422
```

- [ ] **Step 7.3:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_budgets.py -v
```

期望:已有 4 个 PASS + 新增 4 个 PASS = 8 个全 PASS。

- [ ] **Step 7.4:Commit**

```powershell
git add backend/app/api/budgets.py backend/tests/api/test_budgets.py
git commit -m "feat(api): PUT /budgets upsert endpoint"
```

---

## Task A8:API endpoint — `DELETE /budgets/{id}`

**Files:**
- Modify: `backend/app/api/budgets.py`
- Modify: `backend/tests/api/test_budgets.py`

- [ ] **Step 8.1:在 `backend/app/api/budgets.py` 末尾加 DELETE 端点**

```python
from fastapi import Response


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(
    user: CurrentUserDep, db: DbDep,
    budget_id: int,
) -> Response:
    from sqlalchemy import select
    b = db.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == user.id)
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "budget not found")
    db.delete(b)
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

(`Response` 和 `select` 在文件中可能未 import,在文件顶部检查并补齐 import)

- [ ] **Step 8.2:追加 DELETE 测试到 `test_budgets.py`**

```python
def test_delete_happy(logged_in_client):
    r = logged_in_client.put("/api/budgets", json={
        "period_year": 2026, "period_month": 5,
        "category_id": None, "amount": "3000", "note": None,
    })
    bid = r.json()["id"]
    r = logged_in_client.delete(f"/api/budgets/{bid}")
    assert r.status_code == 204
    rl = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert rl.json() == []


def test_delete_not_found(logged_in_client):
    r = logged_in_client.delete("/api/budgets/99999")
    assert r.status_code == 404


def test_delete_other_user_404(logged_in_client, db):
    """删别人的 budget 应返 404(避免泄露存在性)。"""
    from app.models import User
    other = User(username="other-user", password_hash="x")
    db.add(other); db.flush()
    b = Budget(user_id=other.id, period_year=2026, period_month=5,
               category_id=None, amount=Decimal("100"))
    db.add(b); db.flush()
    r = logged_in_client.delete(f"/api/budgets/{b.id}")
    assert r.status_code == 404
```

- [ ] **Step 8.3:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_budgets.py -v
```

期望:11 个 test 全 PASS。

- [ ] **Step 8.4:Commit**

```powershell
git add backend/app/api/budgets.py backend/tests/api/test_budgets.py
git commit -m "feat(api): DELETE /budgets/{id} endpoint"
```

---

## Task A9:API endpoint — `POST /budgets/copy-from`

**Files:**
- Modify: `backend/app/api/budgets.py`
- Modify: `backend/tests/api/test_budgets.py`

- [ ] **Step 9.1:在 `backend/app/api/budgets.py` 末尾加 copy-from 端点**

```python
@router.post("/copy-from", response_model=list[BudgetOut])
def copy_from_endpoint(
    user: CurrentUserDep, db: DbDep,
    body: BudgetCopyIn,
) -> list[Budget]:
    created, conflict = copy_budgets_from(
        db,
        user_id=user.id,
        from_year=body.from_year,
        from_month=body.from_month,
        to_year=body.to_year,
        to_month=body.to_month,
    )
    if conflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "target month already has budget entries; clear them first",
        )
    return created
```

- [ ] **Step 9.2:追加 copy-from 测试**

```python
def test_copy_from_happy(logged_in_client, db, admin_user):
    db.add(Budget(user_id=admin_user.id, period_year=2026, period_month=4,
                  category_id=None, amount=Decimal("3000"), note="4 月总"))
    db.flush()
    r = logged_in_client.post("/api/budgets/copy-from", json={
        "from_year": 2026, "from_month": 4,
        "to_year": 2026, "to_month": 5,
    })
    assert r.status_code == 200
    assert len(r.json()) == 1
    rl = logged_in_client.get("/api/budgets?year=2026&month=5")
    assert rl.json()[0]["amount"] == "3000.00"
    assert rl.json()[0]["note"] == "4 月总"


def test_copy_from_empty_source(logged_in_client):
    r = logged_in_client.post("/api/budgets/copy-from", json={
        "from_year": 2026, "from_month": 3,
        "to_year": 2026, "to_month": 5,
    })
    assert r.status_code == 200
    assert r.json() == []


def test_copy_from_target_conflict(logged_in_client, db, admin_user):
    db.add(Budget(user_id=admin_user.id, period_year=2026, period_month=5,
                  category_id=None, amount=Decimal("4000")))
    db.flush()
    r = logged_in_client.post("/api/budgets/copy-from", json={
        "from_year": 2026, "from_month": 4,
        "to_year": 2026, "to_month": 5,
    })
    assert r.status_code == 409
```

- [ ] **Step 9.3:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_budgets.py -v
```

期望:14 个 test 全 PASS。

- [ ] **Step 9.4:Commit**

```powershell
git add backend/app/api/budgets.py backend/tests/api/test_budgets.py
git commit -m "feat(api): POST /budgets/copy-from endpoint"
```

---

## Task A10:综合验证 + ruff lint

**Files:**
- 无

- [ ] **Step 10.1:跑全部 budget 相关测试**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/models/test_budget.py tests/services/test_budget_service.py tests/api/test_budgets.py -v
```

期望:**24 个 test 全 PASS**(模型 4 + 服务 6 + API 14)。

- [ ] **Step 10.2:跑 ruff 检查**

```powershell
.\.venv\Scripts\python.exe -m ruff check app
```

期望:无错误。如有报错,按提示修复(导入顺序、未使用变量等)。

- [ ] **Step 10.3:跑全部测试,确保没破坏现有功能**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

期望:全绿。如有不通过的测试,看是不是 import 顺序导致循环或 schema __init__ 写错了。

- [ ] **Step 10.4:手动 smoke test**

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

另一个终端:
```powershell
# 登录拿 cookie
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"<your-password>"}' -c cookie.txt -i

# PUT 一条总预算
curl -X PUT http://localhost:8000/api/budgets -H "Content-Type: application/json" -d '{"period_year":2026,"period_month":5,"category_id":null,"amount":"3000","note":"测试"}' -b cookie.txt

# 列出
curl "http://localhost:8000/api/budgets?year=2026&month=5" -b cookie.txt
```

期望:能创建 + 列出。

---

## 切片 A 完成 DoD 复核

回到 [`2026-05-11-dashboard-overview.md`](2026-05-11-dashboard-overview.md) 切片 A 的 DoD 段,对照检查:

- [x] Alembic 迁移在干净 db 跑过,`budgets` 表 + 两个 partial unique index 都存在
- [x] 5 个 API 端点(`GET / PUT / DELETE /budgets`、`POST /budgets/copy-from`)都通过认证 + 业务测试
- [x] 唯一约束:同月同 category(非 NULL)只能一条;同月总预算(category_id IS NULL)只能一条
- [x] copy-from 边界:上月有数据 / 上月无数据 / 目标月已有数据(返 409)三种情况都正确

切片 A 完成。下一步进入 [`2026-05-11-dashboard-slice-b-snapshot-api.md`](2026-05-11-dashboard-slice-b-snapshot-api.md)。
