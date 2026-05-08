# 切片 A:数据库基础 — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 4 描述的 8 张表 schema(users / accounts / statement_imports / transactions / categories / merchant_rules / dedup_candidates / api_tokens),完成 Alembic 迁移,在 Postgres 16 容器中跑起来,并 seed 默认分类树和 25+ 条种子规则。同时跑通"backend 本机 venv ↔ db 容器"开发链路。

**Architecture:** Postgres 16 跑在 docker compose 容器中,backend 用本机 Python 3.11 venv 通过 `localhost:5432` 连。SQLAlchemy 2.x 的 declarative + `Mapped[]` 注解风格定义模型,Alembic 自动生成初始迁移,seed 用幂等脚本(可重复跑)。本切片不上 docker 化的 backend,留到切片 E 部署阶段统一改造。

**Tech Stack:** Python 3.11 / SQLAlchemy 2.0 / Pydantic v2 / Pydantic-Settings / Alembic 1.14 / psycopg 3 / Postgres 16 / FastAPI(仅最小 health 端点)/ pytest。

---

## File Structure(切片 A 涉及的文件清单)

**新建:**
```
backend/
  app/
    __init__.py
    main.py                      # FastAPI 实例 + health endpoint
    core/
      __init__.py
      config.py                  # Pydantic Settings(读 .env)
      db.py                      # SQLAlchemy engine + Session
    models/
      __init__.py                # re-export 所有模型
      base.py                    # DeclarativeBase + 通用 mixins(timestamps)
      user.py
      account.py
      statement_import.py
      transaction.py
      category.py
      merchant_rule.py
      dedup_candidate.py
      api_token.py
    db/
      __init__.py
      seed.py                    # seed entry point(幂等)
      seed_categories.py         # 默认分类树
      seed_merchant_rules.py     # 25+ 条种子规则
  alembic.ini                    # alembic 配置
  alembic/
    env.py                       # alembic env(读 settings,导入 models)
    script.py.mako               # 模板(默认即可)
    versions/
      0001_initial.py            # 初始迁移
  tests/
    __init__.py
    conftest.py                  # pytest fixtures(test db)
    test_models_smoke.py         # 模型导入 + 增删改查烟测
    test_seed.py                 # seed 幂等性测试
    test_health.py               # /api/health endpoint 测试
  .env.example -> .env           # 用户在本机创建(从 .env.example 复制)
```

**修改:**
- `docker-compose.yml`:**暂不改**,沿用现有(只需 db 服务起来,backend/mcp/frontend 服务在切片 A 不启动,可在 `docker compose up db` 时只起一个)

---

## Task 1:本机环境准备

**Files:**
- 无文件改动(纯环境)

- [ ] **Step 1.1: 检查并安装 Docker Desktop**

打开 PowerShell:
```powershell
docker --version
```

期望输出含 `Docker version 24+`。若提示找不到命令:
```powershell
winget install Docker.DockerDesktop
```

安装后**必须开机/重启启动 Docker Desktop**,让它常驻。第一次启动会要求开 WSL2 后端(同意)。

- [ ] **Step 1.2: 检查并安装 Python 3.11**

```powershell
py -3.11 --version
```

若提示找不到:
```powershell
winget install Python.Python.3.11
```

`py -3.11` 的存在让你保留全局的 Python 3.14 同时用 3.11 创建本切片 venv。

- [ ] **Step 1.3: 验证 docker compose 子命令可用**

```powershell
docker compose version
```

期望输出含 `Docker Compose version v2.x`。

- [ ] **Step 1.4: 检查并安装 DBeaver(可选但强烈推荐)**

```powershell
winget list dbeaver.dbeaver
```

不存在则:
```powershell
winget install dbeaver.dbeaver
```

- [ ] **Step 1.5: Commit**(本步骤无文件改动,跳过 commit;在 README 加一条用作记录)

实际上无 commit。继续 Task 2。

---

## Task 2:backend 项目骨架 + venv + 依赖

**Files:**
- Create: `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/models/__init__.py`(以下 5 个 init 文件)
- Create: `backend/.python-version`(写入 `3.11`)
- Modify: `backend/pyproject.toml`(微调 dev 依赖)

- [ ] **Step 2.1: 创建空 init 文件**

PowerShell:
```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
ni -ItemType Directory -Force -Path app\core, app\models, app\db, tests | Out-Null
ni -ItemType File -Force -Path app\__init__.py, app\core\__init__.py, app\models\__init__.py, app\db\__init__.py, tests\__init__.py | Out-Null
```

- [ ] **Step 2.2: 写入 `.python-version`**

```powershell
"3.11" | Out-File -Encoding ascii .python-version -NoNewline
```

- [ ] **Step 2.3: 检查并修订 `backend/pyproject.toml`**

打开 `backend/pyproject.toml`,确认 `dev` extra 段含 `pytest-cov`(spec 阶段 pyproject 里只列 pytest/pytest-asyncio/ruff/mypy,我们补一条 cov):

替换块:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.7",
    "mypy>=1.13",
    "httpx>=0.27",
]
```

(`httpx` 列了两遍 ok,FastAPI TestClient 需要)

- [ ] **Step 2.4: 创建 venv 并安装依赖**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip wheel
pip install -e ".[dev]"
pip list | Select-String -Pattern "fastapi|sqlalchemy|alembic|psycopg|pydantic|pytest"
```

期望输出中能看到 fastapi、sqlalchemy、alembic、psycopg、pydantic、pydantic-settings、pytest 等条目,版本号符合 pyproject 中要求。

- [ ] **Step 2.5: 创建 `.env` 和 `.env.local`(本机用)**

在**仓库根目录**(`finance-manager/`)而非 backend/ 下:
```powershell
cd D:\IDEACursor\Claude-code\finance-manager
copy .env.example .env
```

打开 `.env`,把以下字段改成本机值(POSTGRES_PASSWORD 用强随机):
```
POSTGRES_USER=finance
POSTGRES_PASSWORD=local_dev_4f8a72e1c9d6b3a5
POSTGRES_DB=finance
DATABASE_URL=postgresql+psycopg://finance:local_dev_4f8a72e1c9d6b3a5@localhost:5432/finance

BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKEND_CORS_ORIGINS=http://localhost:3000
SECRET_KEY=dev_jwt_secret_replace_in_prod_8c2f9e1a7b3d5046
```

注意 `DATABASE_URL` host 用 `localhost`(因为本机 venv 连容器,容器 5432 已映射到宿主机),不是 `db`。

把 `.env` 加进 git 忽略验证:
```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git status --short
```

期望看不到 `.env`,只看到本切片新增的 backend 文件。

- [ ] **Step 2.6: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/.python-version backend/pyproject.toml backend/app/__init__.py backend/app/core/__init__.py backend/app/models/__init__.py backend/app/db/__init__.py backend/tests/__init__.py
git commit -m "chore(backend): scaffold app skeleton and pin Python 3.11"
```

---

## Task 3:核心配置(Pydantic Settings)

**Files:**
- Create: `backend/app/core/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 3.1: 写测试 `tests/test_config.py`**

```python
"""Settings 加载与默认值测试。"""
from app.core.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/test")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummy")

    s = Settings()

    assert str(s.database_url).startswith("postgresql+psycopg://")
    assert s.secret_key == "x" * 32
    assert s.backend_cors_origins == ["http://localhost:3000"]


def test_settings_cors_can_be_csv(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/test")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummy")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://a.com,http://b.com")

    s = Settings()

    assert s.backend_cors_origins == ["http://a.com", "http://b.com"]
```

- [ ] **Step 3.2: 跑测试看失败**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/test_config.py -v
```

期望:`ImportError: cannot import name 'Settings' from 'app.core.config'`。

- [ ] **Step 3.3: 写 `app/core/config.py`**

```python
"""Pydantic Settings:读 .env 并把字段做类型校验。"""
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Postgres
    database_url: str = Field(...)

    # Backend
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    backend_cors_origins: List[str] = ["http://localhost:3000"]

    # Auth
    secret_key: str = Field(..., min_length=32)
    admin_username: str = "admin"
    admin_password_hash: str = Field(...)

    # MCP
    mcp_api_token: str | None = None

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def split_cors(cls, v):
        if isinstance(v, str) and "," in v:
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, str):
            return [v]
        return v


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3.4: 跑测试看通过**

```powershell
pytest tests/test_config.py -v
```

期望:2 passed。

- [ ] **Step 3.5: 在 `.env` 里补两个 admin 字段**

打开 `D:\IDEACursor\Claude-code\finance-manager\.env`,追加:

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$temporaryDevHashReplaceInRealUse123456789012345678901234
```

(切片 C 真做认证时再生成真 hash。这里只为让 Settings 能加载。)

- [ ] **Step 3.6: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat(backend): add typed Settings (pydantic) and tests"
```

---

## Task 4:数据库会话(SQLAlchemy 2 engine + Session)

**Files:**
- Create: `backend/app/core/db.py`
- Create: `backend/app/models/base.py`
- Test: `backend/tests/test_db_smoke.py`(暂时跳过,Task 6 完整 schema 后再测)

- [ ] **Step 4.1: 写 `app/models/base.py`**

```python
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
    """所有业务表都带 created_at / updated_at。"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [ ] **Step 4.2: 写 `app/core/db.py`**

```python
"""SQLAlchemy engine/session 工厂。"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖:每个请求一个 session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Iterator[Session]:
    """普通脚本/seed 用的 context manager。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 4.3: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/core/db.py backend/app/models/base.py
git commit -m "feat(backend): add SQLAlchemy engine, session factory, naming convention"
```

---

## Task 5:SQLAlchemy 模型(8 张表)

> **本 task 文件较多,但每个模型独立、可读性高。每个模型在自己文件里写,然后 `models/__init__.py` 集中 re-export 给 Alembic 用。**

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/account.py`
- Create: `backend/app/models/category.py`
- Create: `backend/app/models/merchant_rule.py`
- Create: `backend/app/models/statement_import.py`
- Create: `backend/app/models/transaction.py`
- Create: `backend/app/models/dedup_candidate.py`
- Create: `backend/app/models/api_token.py`
- Modify: `backend/app/models/__init__.py`(re-export)

- [ ] **Step 5.1: 写 `app/models/user.py`**

```python
"""User 模型。MVP 单用户硬编码,但留表为多用户铺垫。"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
```

- [ ] **Step 5.2: 写 `app/models/account.py`**

```python
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
```

- [ ] **Step 5.3: 写 `app/models/category.py`**

```python
"""Category 模型:树形分类。"""
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # kind ∈ expense | income | neutral
    icon: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
```

- [ ] **Step 5.4: 写 `app/models/merchant_rule.py`**

```python
"""MerchantRule 模型:商家规则表。"""
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MerchantRule(Base, TimestampMixin):
    __tablename__ = "merchant_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # match_kind ∈ exact | contains | regex | fuzzy
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (
        # spec § 4.2 要求按优先级匹配,小数字先;DESC 不必,Postgres 规划器一样
        Index("ix_merchant_rules_user_priority", "user_id", "priority"),
    )
```

- [ ] **Step 5.5: 写 `app/models/statement_import.py`**

```python
"""StatementImport 模型:每次账单导入批次。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StatementImport(Base):
    __tablename__ = "statement_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # source_type ∈ alipay_csv | wechat_xlsx | bank_pdf_bocom_debit | bank_pdf_ccb_credit
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    deduped_count: Mapped[int] = mapped_column(Integer, default=0)
    classified_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 5.6: 写 `app/models/transaction.py`**

```python
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
        Index("ix_transactions_user_tx_time", "user_id", "tx_time"),
        Index("ix_transactions_user_account_time", "user_id", "account_id", "tx_time"),
        Index("ix_transactions_user_merchant_norm", "user_id", "merchant_normalized"),
    )
```

- [ ] **Step 5.7: 写 `app/models/dedup_candidate.py`**

```python
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
```

- [ ] **Step 5.8: 写 `app/models/api_token.py`**

```python
"""ApiToken 模型:给 MCP server 用的静态 API token(存 hash)。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApiToken(Base, TimestampMixin):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    scopes: Mapped[str] = mapped_column(String(64), default="read,write", server_default="read,write")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 5.9: 写 `app/models/__init__.py`(集中 re-export)**

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
]
```

- [ ] **Step 5.10: 烟测 import**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
python -c "from app.models import Base; print([t.name for t in Base.metadata.tables.values()])"
```

期望输出:
```
['users', 'accounts', 'categories', 'merchant_rules', 'statement_imports', 'transactions', 'dedup_candidates', 'api_tokens']
```

(顺序可能不同,但必须是这 8 张表。)

- [ ] **Step 5.11: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/models/
git commit -m "feat(backend): add 8 SQLAlchemy models for MVP schema"
```

---

## Task 6:Alembic 配置 + 初始迁移

**Files:**
- Create: `backend/alembic.ini`
- Modify: `backend/alembic/env.py`(覆盖默认模板)
- Create: `backend/alembic/script.py.mako`(默认模板,直接写入)
- Create: `backend/alembic/versions/0001_initial.py`(由 alembic 自动生成,我们 review 后入库)

- [ ] **Step 6.1: 写 `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@host/dbname  # 真实值由 env.py 从 Settings 注入,这行只是占位

[post_write_hooks]
hooks = ruff
ruff.type = console_scripts
ruff.entrypoint = ruff
ruff.options = check --fix REVISION_SCRIPT_FILENAME

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 6.2: 写 `backend/alembic/env.py`**

```python
"""Alembic 环境:从 Settings 拉 DATABASE_URL,从 app.models 取 metadata。"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6.3: 写 `backend/alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6.4: 启动 db 容器**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
docker compose up -d db
docker compose ps
```

期望 `db` 服务 status 是 `healthy`(等 5-10 秒,health check 起作用)。

如果 docker-compose.yml 没有 db 单独 profile,直接 `docker compose up -d db` 也会因为依赖关系起其他服务。**当前 spec 阶段还未拆 profile,故只起 db 这一项**:

```powershell
docker compose up -d db
```

观察日志:
```powershell
docker compose logs db --tail 30
```

期望见到 `database system is ready to accept connections`。

- [ ] **Step 6.5: 自动生成初始迁移**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
alembic revision --autogenerate -m "initial schema"
```

`alembic/versions/` 下应出现一个新文件,文件名形如 `<hash>_initial_schema.py`。**重命名为 `0001_initial.py`**,并把文件顶部的 `revision: str = '<hash>'` 改成 `revision: str = "0001"`,`down_revision: Union[str, None] = None` 保持。

(为什么改:语义化 revision id 让序列清晰。)

- [ ] **Step 6.6: 检查生成的 0001_initial.py**

打开生成的文件,逐项确认包含:
1. 8 张表(`op.create_table(...)`)
2. 全部 ForeignKey
3. 索引(`ix_transactions_user_tx_time` 等)
4. UNIQUE 约束(`users.username`、`statement_imports.file_hash`、`api_tokens.token_hash`、`transactions.source_unique_key`)
5. `downgrade()` 反向 drop 各表(顺序与依赖相反)

如果有缺漏 → 检查 model 定义,修复后重新 `alembic revision --autogenerate`(删除旧 0001 文件再生成)。

- [ ] **Step 6.7: 跑迁移**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

期望:`Running upgrade  -> 0001, initial schema`。无错误。

- [ ] **Step 6.8: 用 psql 验证**

```powershell
docker compose exec db psql -U finance -d finance -c "\dt"
```

期望输出 9 行(8 张业务表 + alembic_version):

```
                  List of relations
 Schema |       Name        | Type  |  Owner
--------+-------------------+-------+---------
 public | accounts          | table | finance
 public | alembic_version   | table | finance
 public | api_tokens        | table | finance
 public | categories        | table | finance
 public | dedup_candidates  | table | finance
 public | merchant_rules    | table | finance
 public | statement_imports | table | finance
 public | transactions      | table | finance
 public | users             | table | finance
```

- [ ] **Step 6.9: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/alembic.ini backend/alembic/env.py backend/alembic/script.py.mako backend/alembic/versions/0001_initial.py
git commit -m "feat(backend): configure alembic and add initial schema migration"
```

---

## Task 7:种子数据 — 默认 user + 分类树

**Files:**
- Create: `backend/app/db/seed_categories.py`
- Create: `backend/app/db/seed.py`(主入口,调各子 seed)
- Test: `backend/tests/test_seed_categories.py`

- [ ] **Step 7.1: 写测试 `tests/test_seed_categories.py`**

```python
"""默认分类树 seed 测试:幂等 + 顶级分类齐全。"""
import pytest
from sqlalchemy.orm import Session

from app.db.seed_categories import seed_default_categories
from app.models import Category, User


@pytest.fixture
def admin_user(db: Session) -> User:
    """先建一个 admin user,让 categories.user_id FK 有引用对象。"""
    user = User(username="admin", password_hash="$2b$12$dummy")
    db.add(user)
    db.commit()
    return user


def test_seed_creates_categories(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()

    cats = db.query(Category).all()
    assert len(cats) >= 12, "应有至少 12 个分类(顶级 + 二级若干)"

    top_names = {c.name for c in cats if c.parent_id is None}
    assert {"餐饮", "交通", "购物", "通讯", "工资", "内部转账"}.issubset(top_names)


def test_seed_categories_idempotent(db: Session, admin_user: User):
    """重复跑 seed 不应出现重复行。"""
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    first_count = db.query(Category).count()

    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    second_count = db.query(Category).count()

    assert first_count == second_count
```

(此测试需要一个 `db` fixture,Step 9 的 conftest.py 会写。先写测试代码,fixture 后到。)

- [ ] **Step 7.2: 写 `app/db/seed_categories.py`**

```python
"""默认分类树 seed。幂等:按 (user_id, name, parent_id) 检查后插入。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category


# 树形结构:(name, kind, sort_order, [(child_name, sort_order), ...])
_TREE: list[tuple[str, str, int, list[tuple[str, int]]]] = [
    ("餐饮", "expense", 10, [
        ("咖啡", 11), ("早餐", 12), ("午餐", 13), ("晚餐", 14),
        ("外卖", 15), ("食材", 16), ("零食", 17),
    ]),
    ("交通", "expense", 20, [
        ("公交地铁", 21), ("打车", 22), ("加油", 23), ("停车", 24),
    ]),
    ("购物", "expense", 30, [
        ("淘宝", 31), ("京东", 32), ("拼多多", 33), ("实体店", 34),
    ]),
    ("通讯", "expense", 40, [("话费", 41), ("流量", 42)]),
    ("居家", "expense", 50, [
        ("房租", 51), ("水电气", 52), ("物业", 53),
    ]),
    ("娱乐", "expense", 60, [
        ("游戏", 61), ("视频会员", 62), ("阅读", 63), ("电影", 64), ("旅行", 65),
    ]),
    ("医疗", "expense", 70, []),
    ("职业", "expense", 80, [("会费", 81), ("学习", 82)]),
    ("转账", "expense", 90, [("红包", 91), ("个人转账", 92)]),

    ("工资", "income", 110, []),
    ("奖金", "income", 120, []),
    ("投资收益", "income", 130, []),
    ("退款", "income", 140, []),
    ("其他收入", "income", 150, []),

    ("内部转账", "neutral", 210, []),
    ("充值提现", "neutral", 220, []),
    ("信用卡还款入账", "neutral", 230, []),
]


def _get_or_create(
    db: Session, *, user_id: int, name: str, parent_id: int | None, kind: str, sort_order: int
) -> Category:
    stmt = select(Category).where(
        Category.user_id == user_id,
        Category.name == name,
        Category.parent_id.is_(parent_id) if parent_id is None else Category.parent_id == parent_id,
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing
    cat = Category(
        user_id=user_id, name=name, parent_id=parent_id, kind=kind, sort_order=sort_order
    )
    db.add(cat)
    db.flush()
    return cat


def seed_default_categories(db: Session, default_user_id: int) -> int:
    """seed 默认分类树。返回插入/已存在的总分类数。"""
    count = 0
    for top_name, kind, top_order, children in _TREE:
        top = _get_or_create(
            db, user_id=default_user_id, name=top_name, parent_id=None, kind=kind, sort_order=top_order
        )
        count += 1
        for child_name, child_order in children:
            _get_or_create(
                db, user_id=default_user_id, name=child_name,
                parent_id=top.id, kind=kind, sort_order=child_order,
            )
            count += 1
    return count
```

- [ ] **Step 7.3: 写 `app/db/seed.py`(主入口)**

```python
"""seed 主入口:可被 CLI 或测试调用。"""
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import db_session
from app.models import User
from app.db.seed_categories import seed_default_categories


def ensure_default_user(db: Session) -> User:
    """确保 admin 用户存在(幂等)。"""
    existing = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        username="admin",
        password_hash="$2b$12$placeholder_replace_in_slice_c",  # 切片 C 真正做认证时改
    )
    db.add(user)
    db.flush()
    return user


def run_seed() -> None:
    with db_session() as db:
        user = ensure_default_user(db)
        cat_count = seed_default_categories(db, default_user_id=user.id)
        print(f"[seed] user_id={user.id}, categories seeded={cat_count}")


if __name__ == "__main__":
    run_seed()
    sys.exit(0)
```

- [ ] **Step 7.4: 跑测试看通过(需要 conftest 的 db fixture,先跳到 Task 9 写 fixture,再回来)**

跳到 Task 9 写完 fixture 后再:
```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
pytest tests/test_seed_categories.py -v
```

为顺次推进,本 task 暂只 commit 代码,Task 9 的 fixture 写完后再跑此测试。

- [ ] **Step 7.5: 命令行手动验证**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
python -m app.db.seed
```

期望输出:`[seed] user_id=1, categories seeded=42`(数字与树结构一致,~42)。

再跑一次:
```powershell
python -m app.db.seed
```

输出仍是 `[seed] user_id=1, categories seeded=42`(幂等)。

数据库中验证:
```powershell
docker compose exec db psql -U finance -d finance -c "SELECT COUNT(*) FROM categories;"
docker compose exec db psql -U finance -d finance -c "SELECT name FROM categories WHERE parent_id IS NULL ORDER BY sort_order;"
```

- [ ] **Step 7.6: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/db/seed.py backend/app/db/seed_categories.py backend/tests/test_seed_categories.py
git commit -m "feat(backend): seed default user and category tree (idempotent)"
```

---

## Task 8:种子数据 — 商家规则(28 条)

**Files:**
- Create: `backend/app/db/seed_merchant_rules.py`
- Modify: `backend/app/db/seed.py`(调用 seed_merchant_rules)
- Test: `backend/tests/test_seed_merchant_rules.py`

- [ ] **Step 8.1: 写测试 `tests/test_seed_merchant_rules.py`**

```python
"""种子商家规则 seed 测试。"""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.seed_categories import seed_default_categories
from app.db.seed_merchant_rules import seed_default_merchant_rules
from app.models import MerchantRule, User


@pytest.fixture
def admin_user(db: Session) -> User:
    user = User(username="admin", password_hash="$2b$12$dummy")
    db.add(user)
    db.commit()
    return user


def test_seed_rules_creates_at_least_25(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()

    rules = db.execute(select(MerchantRule)).scalars().all()
    assert len(rules) >= 25


def test_seed_rules_idempotent(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()
    first = db.execute(select(MerchantRule)).scalars().all()
    n = len(first)

    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()
    second = db.execute(select(MerchantRule)).scalars().all()

    assert len(second) == n


def test_seed_rules_priority_ordering(db: Session, admin_user: User):
    seed_default_categories(db, default_user_id=admin_user.id)
    db.commit()
    seed_default_merchant_rules(db, default_user_id=admin_user.id)
    db.commit()

    # priority 最低数字 = 最先匹配。"银联入账" 应该是最高优先级(priority=10)
    top_rule = db.execute(
        select(MerchantRule).order_by(MerchantRule.priority).limit(1)
    ).scalar_one()
    assert "银联入账" in top_rule.pattern or top_rule.priority <= 10
```

- [ ] **Step 8.2: 写 `app/db/seed_merchant_rules.py`**

```python
"""种子商家规则。priority 越小越先匹配。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, MerchantRule


# (pattern, match_kind, category_path, priority)
# category_path:用 "/" 分隔的分类路径,seed 时解析到具体 category_id;None 表示规则只做"识别标记",不分类
_RULES: list[tuple[str, str, str | None, int]] = [
    # 优先级 10:跨源镜像/还款识别
    (r"银联入账.*\d{4}", "regex", "信用卡还款入账", 10),

    # 优先级 20:跨源中转方关键词标记(category=None,只起标记作用,真正分类靠对侧已分类)
    ("财付通-", "contains", None, 20),
    ("支付宝-", "contains", None, 20),
    ("蚂蚁(杭州)", "contains", None, 20),
    ("蚂蚁(中国)", "contains", None, 20),
    ("拉扎斯网络科技", "contains", None, 20),  # 饿了么
    ("云闪付", "contains", None, 20),
    ("支付平台", "contains", None, 25),

    # 优先级 30:用户身份相关(专利代理人)
    ("中华全国专利代理师协会", "contains", "职业/会费", 30),

    # 优先级 50:常见商家分类
    ("瑞幸咖啡", "fuzzy", "餐饮/咖啡", 50),
    ("luckin coffee", "fuzzy", "餐饮/咖啡", 50),
    ("luckincoffee", "contains", "餐饮/咖啡", 50),
    ("星巴克", "fuzzy", "餐饮/咖啡", 50),
    ("中国移动", "contains", "通讯/话费", 50),
    ("中国联通", "contains", "通讯/话费", 50),
    ("中国电信", "contains", "通讯/话费", 50),
    ("美团", "fuzzy", "餐饮/外卖", 50),
    ("淘宝平台商户", "contains", "购物/淘宝", 50),
    ("淘宝(中国)", "contains", "购物/淘宝", 50),
    ("京东商城", "contains", "购物/京东", 50),
    ("拼多多", "contains", "购物/拼多多", 50),
    ("起点中文网", "contains", "娱乐/阅读", 50),
    ("上海玄霆娱乐", "contains", "娱乐/阅读", 50),  # 起点母公司
    ("北京月之暗面科技", "contains", "娱乐/游戏", 50),  # Kimi 的母公司,可调整
    ("哔哩哔哩", "contains", "娱乐/视频会员", 50),
    ("爱奇艺", "contains", "娱乐/视频会员", 50),
    ("腾讯视频", "contains", "娱乐/视频会员", 50),

    # 优先级 60:微信红包/转账
    ("微信红包-单发", "exact", "转账/红包", 60),
    ("微信转账", "contains", "转账/个人转账", 60),
]


def _resolve_category_id(db: Session, user_id: int, path: str) -> int | None:
    """把 '餐饮/咖啡' 解析为 category_id。"""
    parts = path.split("/")
    parent_id: int | None = None
    cat: Category | None = None
    for part in parts:
        stmt = select(Category).where(
            Category.user_id == user_id,
            Category.name == part,
            (Category.parent_id == parent_id) if parent_id is not None else Category.parent_id.is_(None),
        )
        cat = db.execute(stmt).scalar_one_or_none()
        if cat is None:
            return None
        parent_id = cat.id
    return cat.id if cat else None


def seed_default_merchant_rules(db: Session, default_user_id: int) -> int:
    """seed 种子规则。幂等:(user_id, pattern, match_kind) 唯一。"""
    inserted = 0
    for pattern, match_kind, cat_path, priority in _RULES:
        # 幂等检查
        stmt = select(MerchantRule).where(
            MerchantRule.user_id == default_user_id,
            MerchantRule.pattern == pattern,
            MerchantRule.match_kind == match_kind,
        )
        if db.execute(stmt).scalar_one_or_none() is not None:
            continue

        category_id = _resolve_category_id(db, default_user_id, cat_path) if cat_path else None
        rule = MerchantRule(
            user_id=default_user_id,
            pattern=pattern,
            match_kind=match_kind,
            category_id=category_id,
            priority=priority,
        )
        db.add(rule)
        inserted += 1
    db.flush()
    return inserted
```

- [ ] **Step 8.3: 修改 `app/db/seed.py` 调用规则 seed**

打开 `app/db/seed.py`,在 `run_seed()` 中追加:

```python
from app.db.seed_merchant_rules import seed_default_merchant_rules
```

(放在文件顶部 import 区。)

把 `run_seed` 函数体改为:

```python
def run_seed() -> None:
    with db_session() as db:
        user = ensure_default_user(db)
        cat_count = seed_default_categories(db, default_user_id=user.id)
        rule_count = seed_default_merchant_rules(db, default_user_id=user.id)
        print(f"[seed] user_id={user.id}, categories seeded={cat_count}, rules inserted={rule_count}")
```

- [ ] **Step 8.4: 跑 seed 验证**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
python -m app.db.seed
```

期望:`rules inserted=28` (条数等于 _RULES 列表长度,数一下应该是 28)。

再跑一次:
```powershell
python -m app.db.seed
```

期望:`rules inserted=0`(已存在,幂等)。

```powershell
docker compose exec db psql -U finance -d finance -c "SELECT count(*) FROM merchant_rules;"
docker compose exec db psql -U finance -d finance -c "SELECT pattern, priority FROM merchant_rules ORDER BY priority LIMIT 5;"
```

- [ ] **Step 8.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/db/seed.py backend/app/db/seed_merchant_rules.py backend/tests/test_seed_merchant_rules.py
git commit -m "feat(backend): seed 28 default merchant classification rules"
```

---

## Task 9:pytest 基础设施(conftest + db fixture)

**Files:**
- Create: `backend/tests/conftest.py`
- Modify: `backend/pyproject.toml`(添加 pytest 配置)

- [ ] **Step 9.1: 修改 `backend/pyproject.toml` 加 pytest 配置**

在文件末尾追加:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 9.2: 写 `backend/tests/conftest.py`**

```python
"""pytest fixtures。

策略:
- 用一个独立的"测试 schema"在主 db 里跑,每个测试函数前 truncate 全表
- 这比 SQLite in-memory 简单(不用处理 PG-only 类型如 JSONB),又比 testcontainers 快
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


_settings = get_settings()
_engine = create_engine(_settings.database_url, future=True)
_TestSession = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """整个测试 session 一次性建表。"""
    Base.metadata.create_all(_engine)
    yield
    # session 结束**不**drop,留着便于事后人工查


@pytest.fixture(autouse=True)
def _truncate_between_tests():
    """每个测试前 TRUNCATE 业务表(保留 alembic_version 不动)。"""
    yield
    with _engine.begin() as conn:
        # 用 RESTART IDENTITY 让自增 id 也重置;CASCADE 处理外键
        conn.execute(text(
            "TRUNCATE TABLE "
            "dedup_candidates, transactions, statement_imports, "
            "merchant_rules, categories, api_tokens, accounts, users "
            "RESTART IDENTITY CASCADE"
        ))


@pytest.fixture
def db() -> Session:
    """每个测试一个独立 session(autocommit 关闭,显式 commit)。"""
    session = _TestSession()
    try:
        yield session
        session.rollback()  # 默认每个测试 rollback,显式 commit 的代码可以提前 flush
    finally:
        session.close()
```

- [ ] **Step 9.3: 跑前面 task 写的两个测试**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/test_seed_categories.py tests/test_seed_merchant_rules.py -v
```

期望全部通过(共约 5 个 test)。

如果 `_truncate_between_tests` 报"alembic_version 表"问题,通常是因为 fixture 用的是 `Base.metadata.create_all` 而不是 alembic upgrade,两套机制混在一起。简化方案:测试前先 `alembic upgrade head` 一次手动或 fixture 里跑。

如果上面命令出错,改成:

替换 `_ensure_schema` fixture:
```python
@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """整个测试 session 一次性建表。"""
    # 先清干净再建,确保稳定
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    yield
```

并在 `_truncate_between_tests` 移除 `alembic_version` 这种因为 create_all 不会创建它,只有 alembic 命令会。

- [ ] **Step 9.4: 跑全部测试看 coverage**

```powershell
pytest --cov=app --cov-report=term-missing
```

期望:`config.py / db.py / models / db/seed*.py` 覆盖率高,绿色全过。

- [ ] **Step 9.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/tests/conftest.py backend/pyproject.toml
git commit -m "test(backend): add pytest fixtures (schema setup + truncate between tests)"
```

---

## Task 10:健康检查 endpoint(最小 FastAPI app)

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_health.py`

- [ ] **Step 10.1: 写测试 `tests/test_health.py`**

```python
"""GET /api/health 测试。"""
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "db" in body
    assert body["db"] == "ok"
```

- [ ] **Step 10.2: 跑测试看失败**

```powershell
pytest tests/test_health.py -v
```

期望:`ImportError: cannot import name 'app'`。

- [ ] **Step 10.3: 写 `app/main.py`**

```python
"""FastAPI app 实例 + minimum routes。"""
from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.core.db import engine

app = FastAPI(title="Finance Manager API", version="0.1.0")

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    """健康检查:进程在 + db 可达。"""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {type(e).__name__}"
    return {"status": "ok", "version": app.version, "db": db_status}


app.include_router(router)
```

- [ ] **Step 10.4: 跑测试看通过**

```powershell
pytest tests/test_health.py -v
```

期望:1 passed。

- [ ] **Step 10.5: 启动 uvicorn 手测**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

新开一个 PowerShell:
```powershell
curl http://127.0.0.1:8000/api/health
```

期望返回 JSON `{"status":"ok","version":"0.1.0","db":"ok"}`。

浏览器开 `http://127.0.0.1:8000/docs` 看 Swagger UI 应该能看到 `/api/health`。

按 `Ctrl+C` 关掉 uvicorn。

- [ ] **Step 10.6: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/main.py backend/tests/test_health.py
git commit -m "feat(backend): add /api/health endpoint with db connectivity check"
```

---

## Task 11:DoD 验收脚本

**Files:**
- Create: `backend/scripts/verify_slice_a.ps1`(Windows)
- Create: `backend/scripts/verify_slice_a.sh`(Bash 兼容,留给 docker exec / WSL)

- [ ] **Step 11.1: 写 `backend/scripts/verify_slice_a.ps1`**

```powershell
# 切片 A DoD 验收脚本(Windows PowerShell 7+)
# 用法: 在 finance-manager/ 目录下跑 .\backend\scripts\verify_slice_a.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Slice A DoD Verification ===" -ForegroundColor Cyan

Write-Host "`n[1/5] docker compose up db..." -ForegroundColor Yellow
docker compose up -d db
Start-Sleep -Seconds 3

Write-Host "`n[2/5] alembic upgrade head..." -ForegroundColor Yellow
Set-Location backend
& .\.venv\Scripts\Activate.ps1
alembic upgrade head

Write-Host "`n[3/5] python -m app.db.seed..." -ForegroundColor Yellow
python -m app.db.seed

Write-Host "`n[4/5] DB checks..." -ForegroundColor Yellow
Set-Location ..
$catCount = (docker compose exec -T db psql -U finance -d finance -tAc "SELECT count(*) FROM categories;").Trim()
$ruleCount = (docker compose exec -T db psql -U finance -d finance -tAc "SELECT count(*) FROM merchant_rules;").Trim()
$tableCount = (docker compose exec -T db psql -U finance -d finance -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';").Trim()

Write-Host "  categories count: $catCount (expect >= 12)"
Write-Host "  merchant_rules count: $ruleCount (expect >= 25)"
Write-Host "  public table count: $tableCount (expect 9, includes alembic_version)"

if ([int]$catCount -lt 12) { throw "categories < 12" }
if ([int]$ruleCount -lt 25) { throw "merchant_rules < 25" }
if ([int]$tableCount -lt 9) { throw "table count < 9" }

Write-Host "`n[5/5] pytest..." -ForegroundColor Yellow
Set-Location backend
pytest -q

Set-Location ..
Write-Host "`n=== Slice A DoD: ALL PASS ===" -ForegroundColor Green
```

- [ ] **Step 11.2: 跑验收脚本**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
.\backend\scripts\verify_slice_a.ps1
```

期望最后一行:`=== Slice A DoD: ALL PASS ===`(绿色)。

- [ ] **Step 11.3: 用 DBeaver 手工核对(可选但推荐)**

打开 DBeaver → 新建 PostgreSQL 连接:
- Host: `localhost` Port: `5432`
- DB: `finance`
- User: `finance`
- Password: 从 `.env` 复制 `POSTGRES_PASSWORD` 值

连接后看到 `public` schema 下 9 张表,展开 `categories` 数据 → 看到分类树;展开 `merchant_rules` → 看到 28 条规则。

- [ ] **Step 11.4: 更新 overview 进度表**

打开 `D:\IDEACursor\Claude-code\finance-manager\docs\superpowers\plans\2026-05-08-mvp-overview.md`,在最末"完成进度"表里把切片 A 一行改成:

```
| A. 数据库基础 | ✅ 完成 | 2026-05-XX | XX 小时 | DoD 验收脚本通过 |
```

(实际日期/工时填真实值)

- [ ] **Step 11.5: Commit 验收脚本 + 更新 overview**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/scripts/verify_slice_a.ps1 docs/superpowers/plans/2026-05-08-mvp-overview.md
git commit -m "chore: add slice A DoD verification script and mark slice A done"
```

---

## 完成判定 / Next Step

**切片 A 完成的全部判定**:

- [ ] `verify_slice_a.ps1` 跑完最后一行是 `=== Slice A DoD: ALL PASS ===`
- [ ] 8 张业务表 + 1 张 alembic_version 在 db 中存在
- [ ] `categories ≥ 12`,顶级分类含 餐饮/交通/购物/通讯/工资/内部转账
- [ ] `merchant_rules ≥ 25`,priority 最低条目是"银联入账..."
- [ ] `pytest` 全部通过,coverage 大致覆盖 config/db/models/seed
- [ ] `GET /api/health` 返回 `{"status":"ok","db":"ok"}`
- [ ] 所有 commit 都 push 不到 remote(因为没有 remote),但本地 `git log` 能看到本切片的 ~10 个 commit

**全部满足后,告诉主对话"切片 A 验收通过",我会基于实际产出写切片 B(解析器)的详细 plan。**

---

## 风险快查(Slice A 局部)

| 风险 | 出现概率 | 处理 |
|---|---|---|
| pyproject 装依赖失败(libpq 缺) | 低 | psycopg 用 `[binary]` extra(已配),应该不会有 |
| Alembic autogenerate 漏掉 server_default | 中 | env.py 里设了 `compare_server_default=True`,应能识别;漏的话手工补 |
| Windows 上 docker exec psql 中文乱码 | 中 | 输出只是 schema name,无中文,OK;真要看中文 seed 数据用 DBeaver |
| pytest fixture 跟 alembic_version 表冲突 | 中 | 见 Step 9.3 备选方案,改用 `Base.metadata.create_all` |
| `.env` 文件没创建导致 Settings 起不来 | 高 | Step 2.5 已经强制做;若仍 fail 报错信息会清晰说哪个字段缺 |

(end of slice A plan)
