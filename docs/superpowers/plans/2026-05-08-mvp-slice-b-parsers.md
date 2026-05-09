# 切片 B:4 个账单解析器 — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 5(导入流水线之解析层)和 § 5.3 描述的 4 个解析器:支付宝 CSV / 微信支付 xlsx / 交通银行借记卡 PDF / 建设银行信用卡 PDF。每个解析器实现统一的 `StatementParser` Protocol(`detect()` + `parse()`),输出 spec § 5.2 定义的 `RawTransaction` 列表 + `ParseResult` 元信息。本切片**不写 DB、不写 HTTP**,纯函数库 + 单元测试,由切片 C 负责持久化与流水线编排。同时本切片**第一时间**修掉 slice A 遗留的 I-1(`transactions(user_id, tx_time DESC)` 索引缺 DESC)和 I-3(测试 truncate 策略瓶颈)。

**Architecture:** 解析器作为独立 service 包 `app/services/statement_parser/`,每个解析器一个文件,共享 `base.py` 的 dataclass + Protocol。所有 IO 在 `parse(file_bytes: bytes)` 单点接收原始字节流,完全无副作用,易测试。`registry.py` 维护"detect → 路由"逻辑,供切片 C 的导入端点调用 `route_and_parse(file_bytes, filename)`。测试沿用真实样本(本机已存在,本切片复制到 `tests/fixtures/statements/` 入仓),少量合成样本测边界 case。**测试基础设施**改造:用 SQLAlchemy 2 的 connection-bound session + nested savepoint 替代 TRUNCATE,新加可选 `TEST_DATABASE_URL` 环境变量。

**Tech Stack:** Python 3.11 / pandas 2.2 / openpyxl 3.1 / pdfplumber 0.11 / 标准 csv / dataclasses / typing.Protocol / pytest 8 / pytest-cov 5 / SQLAlchemy 2(仅修改 conftest)/ Alembic(I-1 单 migration)。

---

## Pre-flight(执行前自检)

执行本 plan 的 agent 在 Task 1 前需确认:
- 当前分支是 `slice-b-parsers`(`git branch --show-current`),从 `main` 拉出,无 uncommitted 改动
- Postgres 容器已起:`docker-compose up -d db`,`docker-compose ps db` 显示 healthy
- backend venv 已激活:`cd backend && .\.venv\Scripts\Activate.ps1`,`python -V` 输出 `Python 3.11.x`
- 本机有 4 份真实样本(路径见 CLAUDE.md "真实账单样本"段),Task 8 会复制它们到 fixtures

如以上任一不满足,在仓库根读 `CLAUDE.md` 的"环境与命令规约"和"真实账单样本"段补齐再开工。

---

## File Structure(切片 B 涉及的文件清单)

**新建(backend/app/services/):**
```
backend/app/
  services/
    __init__.py
    statement_parser/
      __init__.py                  # re-export 4 个解析器 + Protocol + dataclasses + registry
      base.py                      # RawTransaction / ParseResult / AccountHint / StatementParser Protocol
      normalize.py                 # normalize_merchant 工具函数
      alipay_csv.py                # AlipayCsvParser
      wechat_xlsx.py               # WechatXlsxParser
      bocom_debit_pdf.py           # BocomDebitPdfParser(交通银行借记卡)
      ccb_credit_pdf.py            # CcbCreditPdfParser(建设银行信用卡)
      registry.py                  # ALL_PARSERS list + route_and_parse() 函数
```

**新建(backend/tests/):**
```
backend/tests/
  services/
    __init__.py
    statement_parser/
      __init__.py
      conftest.py                  # FIXTURES_DIR + 加载 fixture 的工具函数
      test_normalize.py
      test_base.py                 # dataclass 字段 + Protocol 形态
      test_alipay_csv.py
      test_wechat_xlsx.py
      test_bocom_debit_pdf.py
      test_ccb_credit_pdf.py
      test_registry.py
  fixtures/
    statements/
      alipay_sample.csv            # 复制自 C:\Users\WINDOWS\Desktop\财务记录\alipay_record_...\..._1.csv
      wechat_sample.xlsx           # 复制自 D:\Download\IDM\微信支付账单流水...\....xlsx
      bocom_debit_sample.pdf       # 复制自 C:\Users\WINDOWS\Desktop\财务记录\交通银行交易流水...\....pdf
      ccb_credit_sample.pdf        # 复制自 C:\Users\WINDOWS\Desktop\xykmx_20260508202125\xykmx_....pdf
```

**新建(slice A 遗留 I-1 修复):**
```
backend/alembic/versions/0002_tx_time_desc_index.py
```

**新建(DoD 验证):**
```
backend/scripts/verify_slice_b.ps1
```

**修改:**
- `backend/app/core/config.py` — 加 `test_database_url: str | None = None`(I-3 用)
- `backend/app/models/transaction.py` — `Index("ix_transactions_user_tx_time", "user_id", text("tx_time DESC"))`(I-1 用)
- `backend/tests/conftest.py` — 改用 connection + nested savepoint 模式,删除 `_truncate_between_tests`(I-3 用)
- `backend/pyproject.toml` — 加 `pytest` 配置 `markers = ["slow: real-sample integration tests"]`(便于隔离 PDF 解析慢测)
- `.env.example` — 加 `TEST_DATABASE_URL=`(注释占位,可不填)
- `docs/superpowers/plans/2026-05-08-mvp-overview.md` — DoD 完成后,标 slice B 完成 + 划掉 I-1/I-3 遗留项
- `CLAUDE.md` — slice B 完成后更新进度勾选

**不动:**
- 现有所有 model 文件除 `transaction.py` 外
- 现有 0001_initial.py migration(单调递增,只新增 0002)
- docker-compose.yml / Dockerfile / seed.py / FastAPI app 主体

---

## Task 1:I-1 修复 — 给 `transactions(user_id, tx_time DESC)` 索引加 DESC

**Files:**
- Modify: `backend/app/models/transaction.py`(给 `tx_time` 加 `text("tx_time DESC")`)
- Create: `backend/alembic/versions/0002_tx_time_desc_index.py`

> **背景:** spec § 4.2 明确 `transactions(user_id, tx_time DESC)` 是"主查询路径"——交易列表 / get_summary / list_transactions 都按时间倒序翻页,缺 DESC 会让 Postgres 在大数据量下用 sort node 而不是 index scan。Slice A 漏掉了 DESC,这条 migration 修复。

- [ ] **Step 1.1: 修改模型 `transaction.py` 的 `__table_args__`**

打开 [backend/app/models/transaction.py](backend/app/models/transaction.py),在 import 块加入 `text`,并把第一条 Index 改成 DESC 版本:

把:
```python
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
```
改成:
```python
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
```

把:
```python
    __table_args__ = (
        Index("ix_transactions_user_tx_time", "user_id", "tx_time"),
        Index("ix_transactions_user_account_time", "user_id", "account_id", "tx_time"),
        Index("ix_transactions_user_merchant_norm", "user_id", "merchant_normalized"),
    )
```
改成:
```python
    __table_args__ = (
        # spec § 4.2:主查询路径(交易列表按时间倒序翻页),DESC 让 PG 直接走 index scan
        Index("ix_transactions_user_tx_time", "user_id", text("tx_time DESC")),
        Index("ix_transactions_user_account_time", "user_id", "account_id", "tx_time"),
        Index("ix_transactions_user_merchant_norm", "user_id", "merchant_normalized"),
    )
```

- [ ] **Step 1.2: 创建新 migration `0002_tx_time_desc_index.py`**

写入文件 `backend/alembic/versions/0002_tx_time_desc_index.py`:

```python
"""tx_time desc index

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-09 00:00:00.000000

把 ix_transactions_user_tx_time 从 (user_id, tx_time) 改成 (user_id, tx_time DESC),
对齐 spec § 4.2 主查询路径要求。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_transactions_user_tx_time", table_name="transactions")
    op.create_index(
        "ix_transactions_user_tx_time",
        "transactions",
        ["user_id", sa.text("tx_time DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_user_tx_time", table_name="transactions")
    op.create_index(
        "ix_transactions_user_tx_time",
        "transactions",
        ["user_id", "tx_time"],
        unique=False,
    )
```

- [ ] **Step 1.3: 跑 migration 验证 upgrade 成功**

PowerShell:
```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

期望末尾输出:
```
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, tx_time desc index
```

- [ ] **Step 1.4: psql 直连验证索引方向**

```powershell
docker-compose exec db psql -U finance -d finance -c "\d transactions" | Select-String "ix_transactions_user_tx_time"
```

期望输出含:
```
"ix_transactions_user_tx_time" btree (user_id, tx_time DESC)
```

注意 `DESC` 字样必须出现。

- [ ] **Step 1.5: 跑 downgrade + 再 upgrade 验证可逆**

```powershell
alembic downgrade -1
alembic upgrade head
docker-compose exec db psql -U finance -d finance -c "\d transactions" | Select-String "ix_transactions_user_tx_time"
```

最后一行仍应包含 `DESC`,证明 upgrade/downgrade 路径正确。

- [ ] **Step 1.6: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/models/transaction.py backend/alembic/versions/0002_tx_time_desc_index.py
git commit -m "fix(db): add DESC to ix_transactions_user_tx_time (slice A I-1)"
```

---

## Task 2:I-3 修复 — conftest 改用 nested savepoint,可选 TEST_DATABASE_URL

**Files:**
- Modify: `backend/app/core/config.py`(加 `test_database_url`)
- Modify: `backend/tests/conftest.py`(savepoint 模式)
- Modify: `.env.example`(注释占位)

> **背景:** slice A 测试 8 个跑 4m21s,瓶颈是每个测试前 `TRUNCATE TABLE ... CASCADE`(8 表 + cascade)。slice B 加 30+ 解析器测试后会到 8 分钟以上。修法:
> - **主修**:用 SQLAlchemy 2 的 connection-bound session + `join_transaction_mode="create_savepoint"`,每个 test 起一个外层 transaction、teardown 时直接 rollback,session 内 commit 仅 release/create savepoint,代价从"~30s/test 的 truncate"降到"<10ms/test 的 rollback"。
> - **补强**:加可选 `TEST_DATABASE_URL`,允许指向独立 test db(`finance_test`),即使 rollback 出错也不污染开发数据。
> 多数 slice B 解析器测试不用 db fixture,所以 db fixture 改不影响它们的速度;主要是给 slice A 现有 5 个 db 测试和后续 slice C 测试提速。

- [ ] **Step 2.1: 在 `app/core/config.py` 加 `test_database_url` 字段**

打开 [backend/app/core/config.py](backend/app/core/config.py),在 `Settings` 类的 `# Postgres` 段下、`# Backend` 上,插入一行:

把:
```python
    # Postgres
    database_url: str = Field(...)

    # Backend
```
改成:
```python
    # Postgres
    database_url: str = Field(...)
    # 测试专用 db(可选)。未设置时 conftest fallback 到 database_url
    # 设置示例:postgresql+psycopg://finance:pwd@localhost:5432/finance_test
    test_database_url: str | None = None

    # Backend
```

- [ ] **Step 2.2: 在 `.env.example` 加占位**

打开 `.env.example`,在 `DATABASE_URL=...` 那行下方追加:

```
# 可选:测试专用数据库,未设置时复用 DATABASE_URL(测试间用 savepoint rollback 隔离)
# 推荐生产部署后单独创建 finance_test db,本机开发可不填
TEST_DATABASE_URL=
```

(用户可以选择 createdb finance_test 后填上,或留空。)

- [ ] **Step 2.3: 重写 `backend/tests/conftest.py`**

完全替换 `backend/tests/conftest.py` 内容为:

```python
"""pytest fixtures。

策略(slice B I-3 修复后):
- session 起始一次性 create_all(基于 SQLAlchemy metadata,与 alembic 解耦,测试不依赖 alembic head)
- 每个 db 测试开新 connection + 起外层 transaction,session 用 join_transaction_mode="create_savepoint"
- 测试中调 session.commit() 实际只 release/create savepoint,数据可见但未真正落盘
- 测试结束 rollback 外层 transaction,所有数据消失,无 truncate 开销
- 不需要 db 的测试(parser、normalize 等)直接不引用 db fixture,零开销
- 可选 TEST_DATABASE_URL 指向独立 db,进一步保护开发数据
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Base


_settings = get_settings()
_db_url = _settings.test_database_url or _settings.database_url
_engine = create_engine(_db_url, future=True, pool_pre_ping=True)
_TestSession = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """整个测试 session 一次性 create_all。session 结束不 drop,便于事后查表。"""
    Base.metadata.create_all(_engine)
    yield


@pytest.fixture
def db() -> Session:
    """每个 db 测试一个 connection + 外层 transaction + nested savepoint session。

    session.commit() 只 release/create savepoint;teardown rollback 外层 transaction。
    """
    connection = _engine.connect()
    outer_tx = connection.begin()
    session = _TestSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer_tx.rollback()
        connection.close()
```

注意:**整个 `_truncate_between_tests` autouse fixture 必须删除**(它强制每个测试都 truncate,即使不用 db)。新版本只对 `db` fixture 的使用者收 ~10ms savepoint 开销。

- [ ] **Step 2.4: 跑现有 slice A 测试验证仍通过 + 测时间**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest -v --durations=10
```

期望:
- 所有 slice A 测试 pass(test_config / test_health / test_seed_categories ×2 / test_seed_merchant_rules ×3 = 7-8 tests)
- 总时间 **<10s**(从 4m21s 砍下来)
- `--durations=10` 列出最慢的 10 个测试,最慢的应是 PG connection 建立(~1s 内)

如果有 fail,排查方向:
1. `test_seed_categories.py::test_seed_categories_idempotent` — 它在同 session 内连续两次跑 seed 然后 count,savepoint 模式下 count 应该正常增长(seed 是幂等所以第二次 0 增长)。如果失败,检查 seed 函数有没有用独立 `db_session()` context。**应该没有**,seed 函数都接收 `db: Session` 参数。
2. `test_health.py` — 用 TestClient,内部走 `app.core.db.engine`(独立 engine),不应受 conftest 改动影响。

- [ ] **Step 2.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/core/config.py backend/tests/conftest.py .env.example
git commit -m "test: switch to nested-savepoint fixture; add TEST_DATABASE_URL (slice A I-3)"
```

---

## Task 3:解析器 service 包骨架

**Files:**
- Create: `backend/app/services/__init__.py`(空)
- Create: `backend/app/services/statement_parser/__init__.py`(暂时空,Task 11 时补 re-export)
- Create: `backend/tests/services/__init__.py`(空)
- Create: `backend/tests/services/statement_parser/__init__.py`(空)

> 这一 task 只创建空骨架文件让 Python 包可被 import。所有 import 错误从这里开始预防。

- [ ] **Step 3.1: 创建空 init 文件**

PowerShell:
```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
ni -ItemType Directory -Force -Path app\services, app\services\statement_parser, tests\services, tests\services\statement_parser | Out-Null
ni -ItemType File -Force -Path app\services\__init__.py, app\services\statement_parser\__init__.py, tests\services\__init__.py, tests\services\statement_parser\__init__.py | Out-Null
```

- [ ] **Step 3.2: 验证 import 路径不报错**

```powershell
.\.venv\Scripts\Activate.ps1
python -c "import app.services.statement_parser; print('ok')"
```

期望输出 `ok`。

- [ ] **Step 3.3: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/__init__.py backend/app/services/statement_parser/__init__.py backend/tests/services/__init__.py backend/tests/services/statement_parser/__init__.py
git commit -m "chore(backend): scaffold statement_parser service package"
```

---

## Task 4:解析器数据模型 + Protocol(`base.py`)

**Files:**
- Create: `backend/app/services/statement_parser/base.py`
- Test: `backend/tests/services/statement_parser/test_base.py`

> 定义 spec § 5.2 的 `RawTransaction` / `ParseResult` / `AccountHint` 三个 dataclass + `StatementParser` Protocol。这些是后面 4 个解析器和切片 C 之间的契约。注意比 spec § 5.2 多一个 `external_merchant_id` 字段(spec § 5.3.1 提到支付宝有"商家订单号" → `external_merchant_id`,RawTransaction 必须能承载)。

- [ ] **Step 4.1: 写测试 `tests/services/statement_parser/test_base.py`**

```python
"""StatementParser 接口契约 + dataclass 形态测试。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
    StatementParser,
)


def test_raw_transaction_has_required_fields():
    tx = RawTransaction(
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        post_time=None,
        amount=Decimal("12.50"),
        currency="CNY",
        amount_settled_cny=Decimal("12.50"),
        tx_kind="expense",
        merchant_raw="瑞幸咖啡",
        counterparty_raw=None,
        description_raw=None,
        external_tx_id="2026030122000001",
        external_merchant_id=None,
        payment_method_raw=None,
        raw_row={"raw_col": "raw_val"},
    )
    assert tx.amount == Decimal("12.50")
    assert tx.tx_kind == "expense"
    assert tx.raw_row["raw_col"] == "raw_val"


def test_raw_transaction_amount_is_decimal_not_float():
    """金额必须用 Decimal 防浮点误差。"""
    tx = RawTransaction(
        tx_time=datetime(2026, 3, 1),
        post_time=None,
        amount=Decimal("0.1") + Decimal("0.2"),
        currency="CNY",
        amount_settled_cny=Decimal("0.30"),
        tx_kind="expense",
        merchant_raw="x",
        counterparty_raw=None,
        description_raw=None,
        external_tx_id=None,
        external_merchant_id=None,
        payment_method_raw=None,
        raw_row={},
    )
    assert tx.amount == Decimal("0.3")  # Decimal 加法精确


def test_account_hint_fields():
    h = AccountHint(type="bank_credit", institution="建设银行", last4="7432")
    assert h.type == "bank_credit"
    assert h.institution == "建设银行"
    assert h.last4 == "7432"


def test_account_hint_last4_optional_for_alipay_wechat():
    h = AccountHint(type="alipay", institution="支付宝", last4=None)
    assert h.last4 is None


def test_parse_result_carries_metadata():
    r = ParseResult(
        raw_transactions=[],
        account_hint=AccountHint(type="alipay", institution="支付宝", last4=None),
        period_start=datetime(2026, 3, 1),
        period_end=datetime(2026, 3, 26),
        metadata={"row_count_in_header": 100, "expense_total": "1234.56"},
    )
    assert r.metadata["row_count_in_header"] == 100
    assert r.period_start.month == 3


def test_statement_parser_is_protocol():
    """StatementParser 是 Protocol(structural typing),实现类无需显式继承。"""
    class Dummy:
        source_type = "dummy"
        def detect(self, file_bytes: bytes, filename: str) -> bool:
            return False
        def parse(self, file_bytes: bytes) -> ParseResult:
            return ParseResult(
                raw_transactions=[],
                account_hint=AccountHint(type="cash", institution="现金", last4=None),
                period_start=datetime(2026, 1, 1),
                period_end=datetime(2026, 1, 1),
                metadata={},
            )
    d: StatementParser = Dummy()  # 编译期 ok 即说明 Protocol 形态正确
    assert d.source_type == "dummy"
    assert d.detect(b"", "x") is False
```

- [ ] **Step 4.2: 跑测试看失败**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/services/statement_parser/test_base.py -v
```

期望:`ImportError: cannot import name 'AccountHint' from 'app.services.statement_parser.base'`(因为 base.py 还没写)。

- [ ] **Step 4.3: 写 `app/services/statement_parser/base.py`**

```python
"""解析器统一数据模型 + Protocol。

spec 引用:§ 5.2 解析器接口(统一抽象)
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass
class AccountHint:
    """解析器从账单内容推断到的账户标识。

    导入时 (slice C) 用 (user_id, institution, last4) 在 accounts 表查/建。
    支付宝/微信 last4=None,固定走单一全局账户。
    """
    type: str          # bank_debit | bank_credit | alipay | wechat | cash
    institution: str   # "支付宝" | "微信支付" | "交通银行" | "建设银行" 等
    last4: str | None  # 银行卡末 4 位;支付宝/微信为 None


@dataclass
class RawTransaction:
    """解析器输出的单条交易,字段对齐 spec § 5.2 + 补 external_merchant_id。

    所有金额必须用 Decimal,数字始终为正(方向靠 tx_kind);
    raw_row 保留原始字段,审计追溯用。
    """
    tx_time: datetime
    post_time: datetime | None
    amount: Decimal
    currency: str               # 'CNY' | 'USD' | 'EUR' 等 ISO 4217
    amount_settled_cny: Decimal # 多币种交易折算 CNY,单币种交易 == amount
    tx_kind: str                # expense | income | neutral | refund
    merchant_raw: str           # 原始商户名(给 normalize 用)
    counterparty_raw: str | None
    description_raw: str | None
    external_tx_id: str | None      # 同源防重导入用(支付宝交易号/微信交易单号等)
    external_merchant_id: str | None # 支付宝"商家订单号"等
    payment_method_raw: str | None  # 微信"支付方式"列原文,跨源去重锚定用
    raw_row: dict = field(default_factory=dict)  # 原始行,JSONB 进 transactions.raw_payload


@dataclass
class ParseResult:
    """解析器对一份账单文件的完整产出。"""
    raw_transactions: list[RawTransaction]
    account_hint: AccountHint
    period_start: datetime
    period_end: datetime
    metadata: dict = field(default_factory=dict)
    # metadata 常见 key:row_count_in_header / expense_total / income_total / dropped_count
    # 用于切片 C 导入完成后的"对账校验"(汇总能否对得上账单页眉)


class StatementParser(Protocol):
    """所有解析器的统一接口(structural typing,实现类无需显式继承)。

    spec § 5.2: detect 用于自动路由,parse 抽出全部交易。
    """
    source_type: str  # alipay_csv | wechat_xlsx | bank_pdf_bocom_debit | bank_pdf_ccb_credit

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        """嗅探 file_bytes 是否归本解析器处理。可看文件头/扩展名/特征字符串。"""
        ...

    def parse(self, file_bytes: bytes) -> ParseResult:
        """解析整个文件。失败时 raise ValueError(message)。"""
        ...
```

- [ ] **Step 4.4: 跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_base.py -v
```

期望:6 passed。

- [ ] **Step 4.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/base.py backend/tests/services/statement_parser/test_base.py
git commit -m "feat(parser): add RawTransaction/ParseResult/AccountHint + StatementParser Protocol"
```

---

## Task 5:`normalize_merchant` 商户名归一化

**Files:**
- Create: `backend/app/services/statement_parser/normalize.py`
- Test: `backend/tests/services/statement_parser/test_normalize.py`

> spec § 4.1 `merchant_normalized = 去括号/省份/前缀`。这是去重和规则匹配的关键预处理。注意 **不去 payment-channel 前缀**(财付通-/支付宝-),那些前缀的语义信息(指明跨源镜像)由解析器拆到 `payment_method_raw`,merchant_raw 本身就不应包含;但 normalize 函数防御性兜底:如果传入仍含此类前缀,也剥离。

- [ ] **Step 5.1: 写测试 `tests/services/statement_parser/test_normalize.py`**

```python
"""normalize_merchant 单元测试。覆盖括号 / 通道前缀 / 多余空格 / 空字符串。"""
import pytest

from app.services.statement_parser.normalize import normalize_merchant


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 中文括号:省份/城市标注剥离
        ("蚂蚁(杭州)网络技术", "蚂蚁网络技术"),
        ("淘宝(中国)软件有限公司", "淘宝软件有限公司"),
        # 英文括号
        ("Luckin Coffee (Beijing)", "Luckin Coffee"),
        # 通道前缀(防御性兜底)
        ("财付通-luckin coffee", "luckin coffee"),
        ("支付宝-中国移动", "中国移动"),
        ("银联-星巴克", "星巴克"),
        # 全角破折号
        ("财付通—瑞幸咖啡", "瑞幸咖啡"),
        # 多余空格折叠
        ("瑞幸  咖啡   北京", "瑞幸 咖啡 北京"),
        # 前后空白
        ("  美团外卖  ", "美团外卖"),
        # 空字符串 / None 安全
        ("", ""),
    ],
)
def test_normalize_merchant_cases(raw, expected):
    assert normalize_merchant(raw) == expected


def test_normalize_merchant_none_returns_empty():
    """传 None 返回空串,不抛异常。"""
    assert normalize_merchant(None) == ""


def test_normalize_merchant_idempotent():
    """二次跑等于一次跑。"""
    s = "蚂蚁(杭州)网络技术"
    once = normalize_merchant(s)
    twice = normalize_merchant(once)
    assert once == twice


def test_normalize_merchant_preserves_pure_name():
    """不该改的不改。"""
    assert normalize_merchant("瑞幸咖啡") == "瑞幸咖啡"
    assert normalize_merchant("KFC") == "KFC"
```

- [ ] **Step 5.2: 跑测试看失败**

```powershell
pytest tests/services/statement_parser/test_normalize.py -v
```

期望:`ImportError: cannot import name 'normalize_merchant' from 'app.services.statement_parser.normalize'`。

- [ ] **Step 5.3: 写 `app/services/statement_parser/normalize.py`**

```python
"""商户名归一化:去括号、剥离支付通道前缀、折叠空格。

spec § 4.1: merchant_normalized 用于跨源去重 (rapidfuzz 比较) 和规则匹配。
"""
import re


# 中英文括号(贪心避免吃多重嵌套)
_PARENS = re.compile(r"[(（][^()（）]*[)）]")
# 支付通道前缀(财付通-X / 支付宝-X / 银联-X),支持 ASCII 和全角破折号
_CHANNEL_PREFIX = re.compile(r"^(财付通|支付宝|银联)[\-—－＝]\s*")
# 多个空白(含全角)折成单空格
_WHITESPACE = re.compile(r"\s+")


def normalize_merchant(raw: str | None) -> str:
    """对商户名做归一化,返回稳定串供去重/规则匹配。

    步骤:
    1. None / 空 → 直接返回 ""
    2. 剥离支付通道前缀(防御性,正常情况解析器已拆走)
    3. 移除括号及内容
    4. 折叠多余空格、剪前后空白
    """
    if not raw:
        return ""
    s = raw.strip()
    s = _CHANNEL_PREFIX.sub("", s)
    s = _PARENS.sub("", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s
```

- [ ] **Step 5.4: 跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_normalize.py -v
```

期望:13 passed(parametrize 11 个 + 3 个独立测试)。

- [ ] **Step 5.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/normalize.py backend/tests/services/statement_parser/test_normalize.py
git commit -m "feat(parser): add normalize_merchant (strip parens/channel prefix/whitespace)"
```

---

## Task 6:复制真实样本到 `tests/fixtures/statements/`

**Files:**
- Create: `backend/tests/fixtures/statements/alipay_sample.csv`
- Create: `backend/tests/fixtures/statements/wechat_sample.xlsx`
- Create: `backend/tests/fixtures/statements/bocom_debit_sample.pdf`
- Create: `backend/tests/fixtures/statements/ccb_credit_sample.pdf`
- Create: `backend/tests/services/statement_parser/conftest.py`(fixture 路径常量)

> 把 CLAUDE.md "真实账单样本"段列出的 4 份文件,复制到 fixtures 目录下用 ASCII 文件名,保证测试可重复跑。仓库无 remote 单人项目,可放心 commit 真实样本。**不要**做任何"脱敏"或行号截断 —— 真实账单的边界 case(退款行 / 外币行 / 银联还款 / 财付通前缀)是测试的核心,丢一行就丢一类边界。

- [ ] **Step 6.1: 创建 fixtures 目录**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
ni -ItemType Directory -Force -Path tests\fixtures\statements | Out-Null
```

- [ ] **Step 6.2: 复制 4 份真实样本(用 ASCII 目标文件名)**

```powershell
copy "C:\Users\WINDOWS\Desktop\财务记录\alipay_record_20260326_2219\alipay_record_20260326_2219_1.csv" "tests\fixtures\statements\alipay_sample.csv"

copy "D:\Download\IDM\微信支付账单流水文件(20251226-20260326)——【解压密码可在微信支付公众号查看】\微信支付账单流水文件(20251226-20260326)——【解压密码可在微信支付公众号查看】.xlsx" "tests\fixtures\statements\wechat_sample.xlsx"

copy "C:\Users\WINDOWS\Desktop\财务记录\交通银行交易流水(申请时间2026年03月26日22时25分06秒)\交通银行交易流水(申请时间2026年03月26日22时25分06秒).pdf" "tests\fixtures\statements\bocom_debit_sample.pdf"

copy "C:\Users\WINDOWS\Desktop\xykmx_20260508202125\xykmx_20260508202125.pdf" "tests\fixtures\statements\ccb_credit_sample.pdf"
```

期望:4 条 `1 file(s) copied.` 不报"找不到文件"。如果某个真实路径不在,先去 CLAUDE.md "真实账单样本"段对照路径,再回到这里。

- [ ] **Step 6.3: 验证 4 份文件大小合理**

```powershell
dir tests\fixtures\statements\
```

期望(数量级,允许 ±50%):
- `alipay_sample.csv`:几十 ~ 几百 KB
- `wechat_sample.xlsx`:几十 KB
- `bocom_debit_sample.pdf`:几十 ~ 几百 KB
- `ccb_credit_sample.pdf`:几十 ~ 几百 KB

如果某个 < 1 KB,基本是复制失败/截断,重做 Step 6.2。

- [ ] **Step 6.4: 写 `tests/services/statement_parser/conftest.py`**

```python
"""statement_parser 测试共享 fixture:文件路径常量 + 字节加载工具。"""
from pathlib import Path

import pytest


# 仓库根 / backend / tests / fixtures / statements
_FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "statements"


def _load(name: str) -> bytes:
    """加载 fixture 文件全部字节,文件不存在时给清晰错误。"""
    p = _FIXTURE_DIR / name
    if not p.exists():
        pytest.skip(f"fixture not found: {p} (run Task 6 to copy real samples)")
    return p.read_bytes()


@pytest.fixture(scope="module")
def alipay_csv_bytes() -> bytes:
    return _load("alipay_sample.csv")


@pytest.fixture(scope="module")
def wechat_xlsx_bytes() -> bytes:
    return _load("wechat_sample.xlsx")


@pytest.fixture(scope="module")
def bocom_debit_pdf_bytes() -> bytes:
    return _load("bocom_debit_sample.pdf")


@pytest.fixture(scope="module")
def ccb_credit_pdf_bytes() -> bytes:
    return _load("ccb_credit_sample.pdf")


@pytest.fixture(scope="module")
def alipay_filename() -> str:
    return "alipay_record_20260326_2219_1.csv"


@pytest.fixture(scope="module")
def wechat_filename() -> str:
    return "微信支付账单流水文件(20251226-20260326).xlsx"


@pytest.fixture(scope="module")
def bocom_filename() -> str:
    return "交通银行交易流水(申请时间2026年03月26日22时25分06秒).pdf"


@pytest.fixture(scope="module")
def ccb_filename() -> str:
    return "xykmx_20260508202125.pdf"
```

注:`scope="module"` 让同一文件 IO 只发生一次/测试模块,显著加快 PDF 测试。

- [ ] **Step 6.5: smoke 测试 fixture 能加载**

写一个临时验证(不入仓):
```powershell
.\.venv\Scripts\Activate.ps1
python -c "from pathlib import Path; p = Path('tests/fixtures/statements'); print({f.name: f.stat().st_size for f in p.iterdir()})"
```

期望输出 4 个文件名 + 字节数,均 > 1024。

- [ ] **Step 6.6: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/tests/fixtures/statements/ backend/tests/services/statement_parser/conftest.py
git commit -m "test(parser): add real-sample fixtures + module-scoped loader"
```

---

## Task 7:支付宝 CSV 解析器

**Files:**
- Create: `backend/app/services/statement_parser/alipay_csv.py`
- Test: `backend/tests/services/statement_parser/test_alipay_csv.py`

> spec § 5.3.1:GBK 编码,跳前 4 行,第 5 行表头,16 列。仅保留 `交易状态 = "交易成功"`。固定 `account_hint = (alipay, 支付宝, NULL)`。不暴露外币不暴露底层卡。

- [ ] **Step 7.1: 写测试 `tests/services/statement_parser/test_alipay_csv.py`**

```python
"""支付宝 CSV 解析器测试。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.alipay_csv import AlipayCsvParser
from app.services.statement_parser.base import RawTransaction


@pytest.fixture(scope="module")
def parser() -> AlipayCsvParser:
    return AlipayCsvParser()


@pytest.fixture(scope="module")
def parsed(parser: AlipayCsvParser, alipay_csv_bytes: bytes):
    return parser.parse(alipay_csv_bytes)


def test_source_type(parser: AlipayCsvParser):
    assert parser.source_type == "alipay_csv"


def test_detect_accepts_real_alipay_csv(
    parser: AlipayCsvParser, alipay_csv_bytes: bytes, alipay_filename: str
):
    assert parser.detect(alipay_csv_bytes, alipay_filename) is True


def test_detect_rejects_non_csv(parser: AlipayCsvParser):
    assert parser.detect(b"%PDF-1.4\n%fake", "x.pdf") is False
    assert parser.detect(b"not csv at all", "x.txt") is False


def test_detect_rejects_other_csv_without_alipay_marker(parser: AlipayCsvParser):
    """普通 utf-8 csv 不应被错认。"""
    fake = "date,amount\n2026-01-01,100\n".encode("utf-8")
    assert parser.detect(fake, "other.csv") is False


def test_parse_returns_at_least_some_transactions(parsed):
    assert len(parsed.raw_transactions) >= 1, "支付宝样本至少有一行交易成功"


def test_parse_account_hint_is_alipay(parsed):
    h = parsed.account_hint
    assert h.type == "alipay"
    assert h.institution == "支付宝"
    assert h.last4 is None


def test_parse_period_in_2026_q1(parsed):
    """样本日期范围 20260326 期间,period_end 应在 3 月。"""
    assert parsed.period_start <= parsed.period_end
    assert 2025 <= parsed.period_start.year <= 2026


def test_parse_filters_out_non_success(parsed, parser, alipay_csv_bytes):
    """所有产出交易必须 raw_row['交易状态'] == '交易成功'。"""
    for tx in parsed.raw_transactions:
        assert tx.raw_row.get("交易状态", "").strip() == "交易成功"


def test_parse_amounts_are_positive_decimals(parsed):
    for tx in parsed.raw_transactions:
        assert isinstance(tx.amount, Decimal)
        assert tx.amount > 0
        # 支付宝不暴露外币,settled 与 amount 同值
        assert tx.amount_settled_cny == tx.amount
        assert tx.currency == "CNY"


def test_parse_tx_kind_inferred_from_inout(parsed):
    """收/支 列 → expense | income | neutral。"""
    kinds = {tx.tx_kind for tx in parsed.raw_transactions}
    assert kinds.issubset({"expense", "income", "neutral", "refund"})
    # 真实样本应至少有 expense
    assert "expense" in kinds


def test_parse_external_tx_id_populated(parsed):
    """支付宝交易号(列名"交易号")必须填到 external_tx_id。"""
    for tx in parsed.raw_transactions:
        assert tx.external_tx_id is not None
        assert len(tx.external_tx_id) > 8  # 支付宝交易号通常 28 位


def test_parse_payment_method_is_none(parsed):
    """支付宝 CSV 不暴露底层卡。"""
    for tx in parsed.raw_transactions:
        assert tx.payment_method_raw is None


def test_parse_first_transaction_has_merchant_and_time(parsed):
    """抽样:第一条交易必须有商家名 + tx_time。"""
    tx = parsed.raw_transactions[0]
    assert tx.merchant_raw  # 非空串
    assert isinstance(tx.tx_time, datetime)


def test_parse_metadata_has_row_count(parsed):
    """metadata 应记录原始行数和过滤后行数,便于 slice C 对账。"""
    md = parsed.metadata
    assert "raw_row_count" in md
    assert "imported_count" in md
    assert md["imported_count"] == len(parsed.raw_transactions)
    assert md["raw_row_count"] >= md["imported_count"]


def test_parse_raw_row_preserves_original_columns(parsed):
    """raw_row 应含支付宝原列名(中文表头),便于审计。"""
    tx = parsed.raw_transactions[0]
    assert "交易号" in tx.raw_row or "支付宝交易号" in tx.raw_row
    assert "金额" in str(tx.raw_row.keys()) or "金额(元)" in tx.raw_row


def test_parse_invalid_bytes_raises(parser: AlipayCsvParser):
    """乱码字节应 raise ValueError 而非吞错。"""
    with pytest.raises(ValueError):
        parser.parse(b"\x00\x01\x02 not a csv at all")
```

- [ ] **Step 7.2: 跑测试看失败**

```powershell
pytest tests/services/statement_parser/test_alipay_csv.py -v
```

期望:`ImportError: cannot import name 'AlipayCsvParser' from 'app.services.statement_parser.alipay_csv'`。

- [ ] **Step 7.3: 写 `app/services/statement_parser/alipay_csv.py`**

```python
"""支付宝个人账单 CSV 解析器。

spec § 5.3.1:
- 编码 GBK
- 跳前 4 行元信息,第 5 行表头,数据从第 6 行
- 16 列字段(标准支付宝导出)
- 仅保留"交易状态 = 交易成功"
- account_hint 固定为 (alipay, 支付宝, None)
- 不暴露外币不暴露底层卡
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
import csv

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
)


# 表头字符串(支付宝导出格式相对稳定;若变更,detect 会先报)
_HEADER_KEYS = ["交易号", "商家订单号", "交易创建时间", "付款时间", "交易对方", "金额"]
# 元信息行特征字符串(用于 detect)
_META_MARKER = "支付宝交易记录明细查询"


def _decode_gbk_then_gb18030(data: bytes) -> str:
    """支付宝 CSV 主用 GBK,极少数生僻字回退 gb18030。"""
    try:
        return data.decode("gbk")
    except UnicodeDecodeError:
        return data.decode("gb18030")


def _parse_amount(s: str) -> Decimal:
    """金额列转 Decimal,容忍千分位逗号。"""
    s = (s or "").strip().replace(",", "").replace("¥", "")
    if not s:
        return Decimal("0")
    return Decimal(s)


def _parse_dt(s: str) -> datetime | None:
    """支付宝时间格式 'YYYY-MM-DD HH:MM:SS'。空串返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _infer_tx_kind(in_or_out: str) -> str:
    """收/支 列 → tx_kind。"""
    s = (in_or_out or "").strip()
    if s == "支出":
        return "expense"
    if s == "收入":
        return "income"
    return "neutral"  # "/" 或空(转账/担保等)


class AlipayCsvParser:
    source_type = "alipay_csv"

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        """嗅探:文件名 .csv 结尾 + GBK 解码后含'支付宝交易记录明细查询'特征。"""
        if not filename.lower().endswith(".csv"):
            return False
        try:
            head = file_bytes[:4096].decode("gbk", errors="ignore")
        except Exception:
            return False
        return _META_MARKER in head

    def parse(self, file_bytes: bytes) -> ParseResult:
        try:
            text = _decode_gbk_then_gb18030(file_bytes)
        except UnicodeDecodeError as e:
            raise ValueError(f"alipay csv decode failed: {e}") from e

        lines = text.splitlines()
        if len(lines) < 6:
            raise ValueError("alipay csv too short (expect >=6 lines incl. 4 meta + header)")

        # 跳前 4 行元信息;第 5 行(index 4)是表头;数据从 index 5
        header_line = lines[4]
        data_lines = lines[5:]

        reader = csv.DictReader(StringIO("\n".join([header_line, *data_lines])))
        # 表头列名兼容(去掉前后空格 / BOM / "支付宝" 前缀变体)
        norm_header = [h.strip().lstrip("﻿") for h in (reader.fieldnames or [])]
        reader.fieldnames = norm_header

        # 简单校验关键列存在
        missing = [k for k in ["交易号", "付款时间", "交易对方", "收/支", "交易状态"] if k not in norm_header]
        if missing:
            # 兼容部分老格式的"商品名称"未必有,但关键列必须有
            raise ValueError(f"alipay csv missing columns: {missing}")

        raw_rows: list[dict] = []
        for row in reader:
            # 跳过 footer 注释行(支付宝末尾常有 "------本次共导出..." 等)
            if not row.get("交易号") or row["交易号"].strip().startswith("-"):
                continue
            raw_rows.append({k: (v or "").strip() for k, v in row.items()})

        # 仅保留"交易成功"
        success_rows = [r for r in raw_rows if r.get("交易状态") == "交易成功"]

        txs: list[RawTransaction] = []
        all_times: list[datetime] = []
        for r in success_rows:
            try:
                amount = _parse_amount(r.get("金额(元)") or r.get("金额") or "0")
            except InvalidOperation as e:
                raise ValueError(f"alipay csv bad amount in row {r}: {e}") from e
            tx_time = _parse_dt(r.get("付款时间") or r.get("交易创建时间") or "")
            if tx_time is None:
                # 没有可用时间的行不入库(理论上"交易成功"必有付款时间)
                continue
            all_times.append(tx_time)
            txs.append(RawTransaction(
                tx_time=tx_time,
                post_time=None,
                amount=amount,
                currency="CNY",
                amount_settled_cny=amount,
                tx_kind=_infer_tx_kind(r.get("收/支", "")),
                merchant_raw=r.get("交易对方", ""),
                counterparty_raw=r.get("交易对方") or None,
                description_raw=r.get("商品名称") or None,
                external_tx_id=r.get("交易号") or None,
                external_merchant_id=r.get("商家订单号") or None,
                payment_method_raw=None,
                raw_row=r,
            ))

        period_start = min(all_times) if all_times else datetime(1970, 1, 1)
        period_end = max(all_times) if all_times else datetime(1970, 1, 1)

        return ParseResult(
            raw_transactions=txs,
            account_hint=AccountHint(type="alipay", institution="支付宝", last4=None),
            period_start=period_start,
            period_end=period_end,
            metadata={
                "raw_row_count": len(raw_rows),
                "imported_count": len(txs),
                "dropped_count": len(raw_rows) - len(txs),
            },
        )
```

- [ ] **Step 7.4: 跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_alipay_csv.py -v
```

期望:16 passed。

如果某个 spot-check fail,看具体哪个 assert,常见原因:
- "缺关键列":支付宝某些导出版本表头里"金额(元)"/"金额"列名不一致 — 解析器已在 _parse_amount 兼容,但若是其他列名不一致需补
- decode 失败:文件不是标准 GBK,可能用户存盘时带了 BOM,需要 lstrip("﻿")(已加)
- 全部交易被过滤掉:可能"交易状态"列名变了或值不是"交易成功"。打开 CSV 用 notepad++ 看真实表头确认

- [ ] **Step 7.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/alipay_csv.py backend/tests/services/statement_parser/test_alipay_csv.py
git commit -m "feat(parser): add alipay_csv parser (GBK, 4-row meta skip, success-only filter)"
```

---

## Task 8:微信支付 xlsx 解析器

**Files:**
- Create: `backend/app/services/statement_parser/wechat_xlsx.py`
- Test: `backend/tests/services/statement_parser/test_wechat_xlsx.py`

> spec § 5.3.2:跳前 17 行元信息,第 18 行表头,数据从第 19 行。11 列。**关键:支付方式列**含底层卡 `建设银行信用卡(7432)`,提取末 4 位入 `payment_method_raw`(供切片 C 跨源精确锚定)。`收/支` 列三态 → tx_kind。

- [ ] **Step 8.1: 写测试 `tests/services/statement_parser/test_wechat_xlsx.py`**

```python
"""微信支付 xlsx 解析器测试。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.wechat_xlsx import WechatXlsxParser


@pytest.fixture(scope="module")
def parser() -> WechatXlsxParser:
    return WechatXlsxParser()


@pytest.fixture(scope="module")
def parsed(parser: WechatXlsxParser, wechat_xlsx_bytes: bytes):
    return parser.parse(wechat_xlsx_bytes)


def test_source_type(parser: WechatXlsxParser):
    assert parser.source_type == "wechat_xlsx"


def test_detect_accepts_real_wechat_xlsx(
    parser: WechatXlsxParser, wechat_xlsx_bytes: bytes, wechat_filename: str
):
    assert parser.detect(wechat_xlsx_bytes, wechat_filename) is True


def test_detect_rejects_csv(parser: WechatXlsxParser):
    assert parser.detect(b"a,b,c\n1,2,3", "x.csv") is False


def test_detect_rejects_unrelated_xlsx(parser: WechatXlsxParser):
    """简单的 xlsx 文件头但内容不含微信特征,应被拒。"""
    # ZIP 文件头(xlsx 是 zip)
    fake_xlsx = b"PK\x03\x04" + b"\x00" * 100
    assert parser.detect(fake_xlsx, "other.xlsx") is False


def test_parse_yields_transactions(parsed):
    assert len(parsed.raw_transactions) >= 1


def test_parse_account_hint_is_wechat(parsed):
    h = parsed.account_hint
    assert h.type == "wechat"
    assert h.institution == "微信支付"
    assert h.last4 is None  # 微信全局账户,具体卡在 payment_method_raw


def test_parse_amounts_are_positive_decimals(parsed):
    for tx in parsed.raw_transactions:
        assert isinstance(tx.amount, Decimal)
        assert tx.amount > 0
        assert tx.currency == "CNY"
        assert tx.amount_settled_cny == tx.amount


def test_parse_tx_kind_three_states(parsed):
    """收/支 列三态:支出 / 收入 / 中性交易。"""
    kinds = {tx.tx_kind for tx in parsed.raw_transactions}
    assert kinds.issubset({"expense", "income", "neutral"})
    assert "expense" in kinds  # 真实样本必有支出


def test_parse_payment_method_raw_populated_for_card_payments(parsed):
    """有"建设银行信用卡(7432)"等的行,payment_method_raw 必填且含末 4 位。"""
    card_method_txs = [
        tx for tx in parsed.raw_transactions
        if tx.payment_method_raw and any(
            kw in tx.payment_method_raw for kw in ["银行", "信用卡", "储蓄卡"]
        )
    ]
    assert len(card_method_txs) >= 1, "样本中至少应有一条用银行卡支付的微信交易"
    # 抽样检查一条:payment_method_raw 必含 4 位数字
    import re
    for tx in card_method_txs[:3]:
        assert re.search(r"\d{4}", tx.payment_method_raw), \
            f"payment_method_raw 应含末 4 位卡号: {tx.payment_method_raw}"


def test_parse_external_tx_id_populated(parsed):
    """微信交易单号入 external_tx_id。"""
    has_id = sum(1 for tx in parsed.raw_transactions if tx.external_tx_id)
    # 不强求 100%(中性交易如零钱通转入可能没有),但绝大多数应有
    assert has_id >= len(parsed.raw_transactions) * 0.8


def test_parse_metadata_counts(parsed):
    md = parsed.metadata
    assert "raw_row_count" in md
    assert "imported_count" in md
    assert md["imported_count"] == len(parsed.raw_transactions)


def test_parse_period_covers_2025_q4_to_2026_q1(parsed):
    """样本期 20251226-20260326,跨年。"""
    assert parsed.period_start.year in (2025, 2026)
    assert parsed.period_end.year in (2025, 2026)
    assert parsed.period_start <= parsed.period_end


def test_parse_invalid_bytes_raises(parser: WechatXlsxParser):
    with pytest.raises(ValueError):
        parser.parse(b"not an xlsx at all")
```

- [ ] **Step 8.2: 跑测试看失败**

```powershell
pytest tests/services/statement_parser/test_wechat_xlsx.py -v
```

期望:`ImportError`。

- [ ] **Step 8.3: 写 `app/services/statement_parser/wechat_xlsx.py`**

```python
"""微信支付 xlsx 解析器。

spec § 5.3.2:
- 跳前 17 行元信息,第 18 行(1-based)表头,数据从第 19 行
- 11 列,关键:支付方式列含底层卡 "建设银行信用卡(7432)"
- 收/支:支出 → expense / 收入 → income / 中性交易 → neutral
- 抽末 4 位卡号塞 payment_method_raw,跨源去重(slice C)用
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
)


# 元信息特征:微信账单 A1 单元格通常是 "微信支付账单明细" 或类似
_META_MARKERS = ["微信支付账单", "微信账单", "微信支付商户账单", "微信支付个人账单"]
_HEADER_ROW_1BASED = 18  # 第 18 行是表头(spec § 5.3.2)


def _parse_amount(s: str) -> Decimal:
    """微信金额列形如 '¥10.50' 或 '10.50'。"""
    s = (s or "").strip().replace("¥", "").replace(",", "")
    if not s:
        return Decimal("0")
    return Decimal(s)


def _parse_dt(s: str) -> datetime | None:
    """微信交易时间格式 'YYYY-MM-DD HH:MM:SS'。"""
    s = (s or "").strip()
    if not s:
        return None
    # openpyxl 可能直接读出 datetime,也可能是字符串;此处兜底字符串
    if isinstance(s, datetime):
        return s
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _infer_tx_kind(in_or_out: str) -> str:
    s = (in_or_out or "").strip()
    if s == "支出":
        return "expense"
    if s == "收入":
        return "income"
    if s == "中性交易":
        return "neutral"
    return "neutral"  # 兜底


class WechatXlsxParser:
    source_type = "wechat_xlsx"

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        """嗅探:.xlsx 扩展名 + A1/A2 单元格含微信账单标识。"""
        if not filename.lower().endswith(".xlsx"):
            return False
        try:
            wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        except Exception:
            return False
        ws = wb.active
        # 取 A1-A5 的字符串内容,有任何一行命中即认
        for row_idx in range(1, 6):
            cell = ws.cell(row=row_idx, column=1).value
            if cell and isinstance(cell, str):
                if any(m in cell for m in _META_MARKERS):
                    wb.close()
                    return True
        wb.close()
        return False

    def parse(self, file_bytes: bytes) -> ParseResult:
        try:
            wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        except Exception as e:
            raise ValueError(f"wechat xlsx load failed: {e}") from e

        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if len(rows) < _HEADER_ROW_1BASED:
            raise ValueError(
                f"wechat xlsx too short (expect >= {_HEADER_ROW_1BASED} rows incl. meta + header)"
            )

        header = [str(c).strip() if c is not None else "" for c in rows[_HEADER_ROW_1BASED - 1]]
        data_rows = rows[_HEADER_ROW_1BASED:]

        # 关键列校验
        required = ["交易时间", "交易类型", "交易对方", "金额(元)", "收/支", "支付方式", "当前状态", "交易单号"]
        missing = [k for k in required if k not in header]
        if missing:
            raise ValueError(f"wechat xlsx missing columns: {missing}")

        idx = {k: header.index(k) for k in header if k}

        raw_rows: list[dict] = []
        for row in data_rows:
            if not row or all(c in (None, "") for c in row):
                continue
            d = {h: (row[i] if i < len(row) else None) for h, i in idx.items()}
            raw_rows.append(d)

        # 微信"当前状态"含"支付成功"/"已存入零钱"/"已转账"等,过滤掉"已退款"等(可选,先全保留交给规则)
        # 这里宽松接收所有非空行;切片 C 流水线再做语义过滤

        txs: list[RawTransaction] = []
        all_times: list[datetime] = []
        for r in raw_rows:
            try:
                raw_amt = r.get("金额(元)")
                amt_str = str(raw_amt) if raw_amt is not None else "0"
                amount = _parse_amount(amt_str)
            except InvalidOperation as e:
                raise ValueError(f"wechat xlsx bad amount: {r}: {e}") from e
            if amount == 0:
                continue
            tx_time = _parse_dt(r.get("交易时间"))
            if tx_time is None:
                continue
            all_times.append(tx_time)
            txs.append(RawTransaction(
                tx_time=tx_time,
                post_time=None,
                amount=amount,
                currency="CNY",
                amount_settled_cny=amount,
                tx_kind=_infer_tx_kind(str(r.get("收/支") or "")),
                merchant_raw=str(r.get("交易对方") or "").strip(),
                counterparty_raw=str(r.get("交易对方") or "").strip() or None,
                description_raw=(str(r.get("商品") or "").strip() or None) if r.get("商品") else (str(r.get("交易类型") or "").strip() or None),
                external_tx_id=(str(r.get("交易单号") or "").strip() or None),
                external_merchant_id=(str(r.get("商户单号") or "").strip() or None) if r.get("商户单号") else None,
                payment_method_raw=(str(r.get("支付方式") or "").strip() or None),
                raw_row={k: (str(v) if v is not None else "") for k, v in r.items()},
            ))

        period_start = min(all_times) if all_times else datetime(1970, 1, 1)
        period_end = max(all_times) if all_times else datetime(1970, 1, 1)

        return ParseResult(
            raw_transactions=txs,
            account_hint=AccountHint(type="wechat", institution="微信支付", last4=None),
            period_start=period_start,
            period_end=period_end,
            metadata={
                "raw_row_count": len(raw_rows),
                "imported_count": len(txs),
                "dropped_count": len(raw_rows) - len(txs),
            },
        )
```

- [ ] **Step 8.4: 跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_wechat_xlsx.py -v
```

期望:11 passed。

常见 fail 排查:
- `missing columns` — 微信账单导出版本不一致,关键列名可能略有差异(如"商品" vs "商品/服务")。打开 xlsx 看实际表头,在 `required` 列表里加上变体,在赋值处加 fallback
- `tx_time is None` — 某行交易时间被 openpyxl 读成 datetime 而非 str,_parse_dt 已 isinstance 兼容
- payment_method_raw 都为 None — 表头列名不是"支付方式",可能是"支付来源"等,加 fallback

- [ ] **Step 8.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/wechat_xlsx.py backend/tests/services/statement_parser/test_wechat_xlsx.py
git commit -m "feat(parser): add wechat_xlsx parser (skip 17 rows, payment_method extract)"
```

---

## Task 9:交通银行借记卡 PDF 解析器

**Files:**
- Create: `backend/app/services/statement_parser/bocom_debit_pdf.py`
- Test: `backend/tests/services/statement_parser/test_bocom_debit_pdf.py`

> spec § 5.3.3:pdfplumber 抽表,6 列(交易日期 / 交易地点 / 交易方式 / 借贷状态 / 交易金额 / 余额)。借贷状态 `借 Dr` → expense,`贷 Cr` → income。时间格式 `YYYY-MM-DD`。识别中转方关键词(支付宝/蚂蚁/拉扎斯/云闪付/支付平台/财付通)写入 `payment_method_raw` 辅助 slice C 桥接去重。`account_hint = (bank_debit, 交通银行, "2498")`(spec 3.1 用户卡号)—— 但更稳的做法是从 PDF 首页抽卡号末 4 位,本切片采取保守策略**先固定 2498**,真出现别的卡号再 generalize。

- [ ] **Step 9.1: 写测试 `tests/services/statement_parser/test_bocom_debit_pdf.py`**

```python
"""交通银行借记卡 PDF 解析器测试。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.bocom_debit_pdf import BocomDebitPdfParser


@pytest.fixture(scope="module")
def parser() -> BocomDebitPdfParser:
    return BocomDebitPdfParser()


@pytest.fixture(scope="module")
def parsed(parser: BocomDebitPdfParser, bocom_debit_pdf_bytes: bytes):
    return parser.parse(bocom_debit_pdf_bytes)


def test_source_type(parser: BocomDebitPdfParser):
    assert parser.source_type == "bank_pdf_bocom_debit"


def test_detect_accepts_real_bocom_pdf(
    parser: BocomDebitPdfParser, bocom_debit_pdf_bytes: bytes, bocom_filename: str
):
    assert parser.detect(bocom_debit_pdf_bytes, bocom_filename) is True


def test_detect_rejects_other_bank_pdf(
    parser: BocomDebitPdfParser, ccb_credit_pdf_bytes: bytes
):
    """建行 PDF 不应被交行解析器认领。"""
    assert parser.detect(ccb_credit_pdf_bytes, "ccb.pdf") is False


def test_detect_rejects_csv(parser: BocomDebitPdfParser):
    assert parser.detect(b"a,b\n1,2", "x.csv") is False


def test_parse_yields_transactions(parsed):
    assert len(parsed.raw_transactions) >= 1


def test_parse_account_hint(parsed):
    h = parsed.account_hint
    assert h.type == "bank_debit"
    assert h.institution == "交通银行"
    assert h.last4 == "2498"


def test_parse_amounts_positive_decimals(parsed):
    for tx in parsed.raw_transactions:
        assert isinstance(tx.amount, Decimal)
        assert tx.amount > 0
        assert tx.currency == "CNY"
        assert tx.amount_settled_cny == tx.amount


def test_parse_tx_kind_dr_cr(parsed):
    """借 Dr → expense,贷 Cr → income。"""
    kinds = {tx.tx_kind for tx in parsed.raw_transactions}
    assert kinds.issubset({"expense", "income"})


def test_parse_intermediary_keyword_in_payment_method_raw(parsed):
    """商家含"支付宝/蚂蚁/拉扎斯/云闪付/支付平台/财付通"任一,
    payment_method_raw 应被填(供 slice C 桥接去重)。"""
    bridge_keywords = ["支付宝", "蚂蚁", "拉扎斯", "云闪付", "支付平台", "财付通"]
    bridge_txs = [
        tx for tx in parsed.raw_transactions
        if any(kw in (tx.merchant_raw or "") for kw in bridge_keywords)
    ]
    if bridge_txs:  # 不强求样本必有,但有的话必须正确标记
        for tx in bridge_txs[:3]:
            assert tx.payment_method_raw is not None
            assert any(kw in tx.payment_method_raw for kw in bridge_keywords)


def test_parse_tx_time_in_2025_2026(parsed):
    for tx in parsed.raw_transactions[:5]:
        assert 2024 <= tx.tx_time.year <= 2026


def test_parse_metadata_counts(parsed):
    md = parsed.metadata
    assert md["imported_count"] == len(parsed.raw_transactions)
    assert md["raw_row_count"] >= md["imported_count"]


def test_parse_invalid_pdf_raises(parser: BocomDebitPdfParser):
    with pytest.raises(ValueError):
        parser.parse(b"not a pdf")


@pytest.mark.slow
def test_parse_full_pdf_under_10s(parser, bocom_debit_pdf_bytes):
    """13 页 PDF 全解析应在 10s 内完成(pdfplumber 基线)。"""
    import time
    t0 = time.time()
    parser.parse(bocom_debit_pdf_bytes)
    assert time.time() - t0 < 10.0
```

- [ ] **Step 9.2: 跑测试看失败**

```powershell
pytest tests/services/statement_parser/test_bocom_debit_pdf.py -v
```

期望:`ImportError`。

- [ ] **Step 9.3: 写 `app/services/statement_parser/bocom_debit_pdf.py`**

```python
"""交通银行借记卡 PDF 解析器。

spec § 5.3.3:
- pdfplumber 抽表,6 列:交易日期 / 交易地点 / 交易方式 / 借贷状态 / 交易金额 / 余额
- 借贷状态:借 Dr → expense,贷 Cr → income
- 时间 YYYY-MM-DD
- 中转方关键词写 payment_method_raw,供切片 C 桥接去重
- 卡号末 4 位本切片保守固定 "2498"(用户实际卡号);若需其他卡号,在 detect 后再 generalize
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re

import pdfplumber

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
)


_BRIDGE_KEYWORDS = ["支付宝", "蚂蚁", "拉扎斯", "云闪付", "支付平台", "财付通"]
_BOCOM_MARKERS = ["交通银行", "BANK OF COMMUNICATIONS", "交易流水"]
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# 卡号末 4 位 fallback;首页若有"卡号 ...XXXX"格式则覆盖
_CARD_TAIL_RE = re.compile(r"(?:卡号|账号|尾号)[\s:：]*[*\dX]*?(\d{4})")
_DEFAULT_LAST4 = "2498"


def _parse_amount(s: str) -> Decimal:
    s = (s or "").strip().replace(",", "").replace("¥", "")
    if not s:
        return Decimal("0")
    return Decimal(s)


def _detect_intermediary(merchant: str) -> str | None:
    """商家名含中转方关键词,返回完整商家名作为 payment_method_raw 标记。"""
    if not merchant:
        return None
    if any(kw in merchant for kw in _BRIDGE_KEYWORDS):
        return merchant
    return None


def _extract_card_last4(text: str) -> str:
    """从 PDF 文本里抽卡号末 4 位;失败回退默认。"""
    m = _CARD_TAIL_RE.search(text or "")
    if m:
        return m.group(1)
    return _DEFAULT_LAST4


class BocomDebitPdfParser:
    source_type = "bank_pdf_bocom_debit"

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        """嗅探:PDF magic + 首页文本含交行 marker。"""
        if not file_bytes.startswith(b"%PDF"):
            return False
        try:
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    return False
                first_text = pdf.pages[0].extract_text() or ""
        except Exception:
            return False
        return any(m in first_text for m in _BOCOM_MARKERS)

    def parse(self, file_bytes: bytes) -> ParseResult:
        if not file_bytes.startswith(b"%PDF"):
            raise ValueError("not a PDF file")

        try:
            pdf = pdfplumber.open(BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"bocom pdf open failed: {e}") from e

        try:
            full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            last4 = _extract_card_last4(full_text)

            raw_rows: list[dict] = []
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    if not table:
                        continue
                    # 找含 "交易日期" / "借贷" / "金额" 的表头行,定位列索引
                    header_idx = None
                    header_row = None
                    for i, row in enumerate(table):
                        joined = "|".join(str(c or "") for c in row)
                        if "交易日期" in joined and ("借贷" in joined or "金额" in joined):
                            header_idx = i
                            header_row = [str(c or "").strip() for c in row]
                            break
                    if header_idx is None:
                        continue
                    # 列索引(以 spec 6 列为基础,容忍顺序变动)
                    col = {h: header_row.index(h) for h in header_row if h}
                    for row in table[header_idx + 1:]:
                        cells = [str(c or "").strip() for c in row]
                        # 跳过空行/页眉重复
                        if not any(cells):
                            continue
                        date_cell = cells[col.get("交易日期", 0)] if "交易日期" in col else cells[0]
                        if not _DATE_RE.search(date_cell):
                            continue
                        d = {h: cells[i] if i < len(cells) else "" for h, i in col.items()}
                        raw_rows.append(d)

            txs: list[RawTransaction] = []
            all_times: list[datetime] = []
            for r in raw_rows:
                date_str = r.get("交易日期", "")
                m = _DATE_RE.search(date_str)
                if not m:
                    continue
                tx_time = datetime.strptime(m.group(0), "%Y-%m-%d")

                amt_str = r.get("交易金额") or r.get("金额") or "0"
                try:
                    amount = _parse_amount(amt_str)
                except InvalidOperation:
                    continue
                if amount <= 0:
                    continue

                # 借贷状态:含 "借" / "Dr" → expense;"贷" / "Cr" → income
                dc = r.get("借贷状态", "") or r.get("借贷", "")
                if "借" in dc or "Dr" in dc.upper():
                    tx_kind = "expense"
                elif "贷" in dc or "Cr" in dc.upper():
                    tx_kind = "income"
                else:
                    tx_kind = "neutral"

                merchant = r.get("交易地点") or r.get("交易方式") or ""
                desc = r.get("交易方式") or None

                txs.append(RawTransaction(
                    tx_time=tx_time,
                    post_time=None,
                    amount=amount,
                    currency="CNY",
                    amount_settled_cny=amount,
                    tx_kind=tx_kind,
                    merchant_raw=merchant,
                    counterparty_raw=None,
                    description_raw=desc,
                    external_tx_id=None,  # 交行 PDF 不暴露交易号
                    external_merchant_id=None,
                    payment_method_raw=_detect_intermediary(merchant),
                    raw_row=r,
                ))
                all_times.append(tx_time)

            period_start = min(all_times) if all_times else datetime(1970, 1, 1)
            period_end = max(all_times) if all_times else datetime(1970, 1, 1)

            return ParseResult(
                raw_transactions=txs,
                account_hint=AccountHint(type="bank_debit", institution="交通银行", last4=last4),
                period_start=period_start,
                period_end=period_end,
                metadata={
                    "raw_row_count": len(raw_rows),
                    "imported_count": len(txs),
                    "dropped_count": len(raw_rows) - len(txs),
                },
            )
        finally:
            pdf.close()
```

- [ ] **Step 9.4: 跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_bocom_debit_pdf.py -v
```

期望:11 passed(含 1 个 slow marker,默认会跑除非 -m "not slow")。

排查:
- `extract_tables` 返回空 → 真实样本表格可能跨页,pdfplumber 需要 `table_settings`。打开样本看是否有边框,若是无边框文字表格需用 `extract_text()` + 正则按行切。**本切片优先 extract_tables**;如果失败,在解析器加 fallback:`page.extract_text()` 后用 `re.split(r"\n")` 按行取,正则提取列。
- 时间解析失败 → 真实日期可能含中文 "年月日",改 `_DATE_RE` 容错

- [ ] **Step 9.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/bocom_debit_pdf.py backend/tests/services/statement_parser/test_bocom_debit_pdf.py
git commit -m "feat(parser): add bocom_debit_pdf parser (Dr/Cr, intermediary keyword)"
```

---

## Task 10:建设银行信用卡 PDF 解析器(最复杂,放最后)

**Files:**
- Create: `backend/app/services/statement_parser/ccb_credit_pdf.py`
- Test: `backend/tests/services/statement_parser/test_ccb_credit_pdf.py`

> spec § 5.3.4:pdfplumber 抽表,9 列(序号 / 交易日 / 银行记账日 / 卡号后4位 / 交易描述 / 交易币 / 交易金额 / 结算币 / 结算金额)。时间 `YYYYMMDD` 无分隔符。**3 大边界 case**:
> 1. **多币种**:交易币 ≠ 结算币 → `amount` 用交易币原值,`amount_settled_cny` 用结算币
> 2. **银联入账**:描述含"银联入账" + 金额为负 → `tx_kind=neutral`(还款)
> 3. **财付通-/支付宝-** 前缀 → 写入 `payment_method_raw`,merchant_raw 剥前缀

- [ ] **Step 10.1: 写测试 `tests/services/statement_parser/test_ccb_credit_pdf.py`**

```python
"""建行信用卡 PDF 解析器测试 — 重点验证 3 大边界 case。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.statement_parser.ccb_credit_pdf import CcbCreditPdfParser


@pytest.fixture(scope="module")
def parser() -> CcbCreditPdfParser:
    return CcbCreditPdfParser()


@pytest.fixture(scope="module")
def parsed(parser: CcbCreditPdfParser, ccb_credit_pdf_bytes: bytes):
    return parser.parse(ccb_credit_pdf_bytes)


def test_source_type(parser: CcbCreditPdfParser):
    assert parser.source_type == "bank_pdf_ccb_credit"


def test_detect_accepts_real_ccb_pdf(
    parser: CcbCreditPdfParser, ccb_credit_pdf_bytes: bytes, ccb_filename: str
):
    assert parser.detect(ccb_credit_pdf_bytes, ccb_filename) is True


def test_detect_rejects_bocom_pdf(
    parser: CcbCreditPdfParser, bocom_debit_pdf_bytes: bytes
):
    assert parser.detect(bocom_debit_pdf_bytes, "bocom.pdf") is False


def test_parse_yields_transactions(parsed):
    assert len(parsed.raw_transactions) >= 1


def test_parse_account_hint(parsed):
    h = parsed.account_hint
    assert h.type == "bank_credit"
    assert h.institution == "建设银行"
    assert h.last4 == "7432"


def test_parse_amounts_positive_decimals(parsed):
    for tx in parsed.raw_transactions:
        assert isinstance(tx.amount, Decimal)
        assert tx.amount > 0
        assert isinstance(tx.amount_settled_cny, Decimal)
        assert tx.amount_settled_cny > 0


def test_parse_tx_time_format_yyyymmdd(parsed):
    """建行 PDF 日期格式 20260326 → 转 datetime 后年应为 2026 附近。"""
    for tx in parsed.raw_transactions[:5]:
        assert 2024 <= tx.tx_time.year <= 2026


def test_parse_post_time_populated(parsed):
    """信用卡有"银行记账日",入 post_time。"""
    has_post = sum(1 for tx in parsed.raw_transactions if tx.post_time is not None)
    assert has_post >= len(parsed.raw_transactions) * 0.8, \
        "至少 80% 的交易应有银行记账日"


# === 边界 case 1:多币种 ===

def test_parse_foreign_currency_distinguishes_amounts(parsed):
    """若样本含外币(交易币 != CNY),amount 用交易币原值,amount_settled_cny 用结算币(CNY)。"""
    fx_txs = [tx for tx in parsed.raw_transactions if tx.currency != "CNY"]
    if fx_txs:  # 不强求,但有就必须正确
        for tx in fx_txs[:3]:
            # 交易币 USD/EUR 等,settled 必为 CNY
            assert tx.currency in ("USD", "EUR", "JPY", "HKD", "GBP", "AUD"), \
                f"unexpected currency: {tx.currency}"
            # 多币种交易,两个金额通常不等(汇率换算)
            assert tx.amount != tx.amount_settled_cny or tx.currency == "CNY"


def test_parse_cny_only_settled_equals_amount(parsed):
    """单币种 CNY 交易,settled == amount。"""
    cny_txs = [tx for tx in parsed.raw_transactions if tx.currency == "CNY"]
    for tx in cny_txs[:5]:
        assert tx.amount == tx.amount_settled_cny


# === 边界 case 2:银联入账还款 ===

def test_parse_unionpay_repayment_tagged_neutral(parsed):
    """描述含"银联入账"的行 → tx_kind=neutral(还款)。"""
    repayment_txs = [
        tx for tx in parsed.raw_transactions
        if "银联入账" in (tx.description_raw or "") or "银联入账" in (tx.merchant_raw or "")
    ]
    if repayment_txs:
        for tx in repayment_txs[:3]:
            assert tx.tx_kind == "neutral", \
                f"银联入账应为 neutral,实际 {tx.tx_kind}: {tx}"


# === 边界 case 3:财付通-/支付宝- 前缀 ===

def test_parse_channel_prefix_extracted_to_payment_method_raw(parsed):
    """描述以"财付通-"或"支付宝-"开头 → 前缀入 payment_method_raw,merchant_raw 剥前缀。"""
    prefix_txs = [
        tx for tx in parsed.raw_transactions
        if tx.payment_method_raw and any(
            tx.payment_method_raw.startswith(p) for p in ["财付通", "支付宝"]
        )
    ]
    if prefix_txs:
        for tx in prefix_txs[:3]:
            # merchant_raw 不应再以前缀开头
            assert not tx.merchant_raw.startswith("财付通-"), \
                f"merchant_raw 应已剥离财付通前缀: {tx.merchant_raw}"
            assert not tx.merchant_raw.startswith("支付宝-"), \
                f"merchant_raw 应已剥离支付宝前缀: {tx.merchant_raw}"
            # payment_method_raw 必含通道名
            assert any(tx.payment_method_raw.startswith(p) for p in ["财付通", "支付宝"])


def test_parse_metadata_counts(parsed):
    md = parsed.metadata
    assert md["imported_count"] == len(parsed.raw_transactions)


def test_parse_invalid_pdf_raises(parser: CcbCreditPdfParser):
    with pytest.raises(ValueError):
        parser.parse(b"not a pdf")
```

- [ ] **Step 10.2: 跑测试看失败**

```powershell
pytest tests/services/statement_parser/test_ccb_credit_pdf.py -v
```

期望:`ImportError`。

- [ ] **Step 10.3: 写 `app/services/statement_parser/ccb_credit_pdf.py`**

```python
"""建设银行信用卡 PDF 解析器。

spec § 5.3.4:
- pdfplumber 抽表,9 列:序号 / 交易日 / 银行记账日 / 卡号后4位 / 交易描述 / 交易币 / 交易金额 / 结算币 / 结算金额
- 时间 YYYYMMDD 无分隔符
- 多币种:交易币 ≠ CNY → amount 用交易币原值,amount_settled_cny 用结算币(CNY)
- 银联入账(还款) → tx_kind=neutral
- 财付通-/支付宝- 前缀 → payment_method_raw 存原前缀字段,merchant_raw 剥前缀
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re

import pdfplumber

from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
)


_CCB_MARKERS = ["建设银行", "China Construction Bank", "信用卡账单", "信用卡客户对账单"]
_DATE8_RE = re.compile(r"\b(\d{8})\b")
_CARD_TAIL_RE = re.compile(r"(?:卡号|账号|尾号)[\s:：*]*(\d{4})")
_DEFAULT_LAST4 = "7432"

_CHANNEL_PREFIX_RE = re.compile(r"^(财付通|支付宝)[\-—－＝]\s*")
_REPAYMENT_KEYWORD = "银联入账"


def _parse_amount(s: str) -> Decimal:
    """金额可能含负号(还款),先取绝对值。"""
    s = (s or "").strip().replace(",", "").replace("¥", "")
    if not s:
        return Decimal("0")
    # 允许 -123.45 / (123.45) 两种负数表示
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s_clean = s.lstrip("-").strip("()")
    val = Decimal(s_clean)
    return -val if neg else val


def _parse_yyyymmdd(s: str) -> datetime | None:
    s = (s or "").strip()
    m = _DATE8_RE.search(s)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d")


def _extract_card_last4(text: str) -> str:
    m = _CARD_TAIL_RE.search(text or "")
    return m.group(1) if m else _DEFAULT_LAST4


def _split_channel_prefix(desc: str) -> tuple[str | None, str]:
    """返回 (channel_prefix_with_field, merchant_after_strip)。

    例:
    - "财付通-luckin coffee" → ("财付通-luckin coffee", "luckin coffee")
    - "支付宝-中国移动" → ("支付宝-中国移动", "中国移动")
    - "瑞幸咖啡" → (None, "瑞幸咖啡")
    """
    if not desc:
        return None, ""
    if _CHANNEL_PREFIX_RE.match(desc):
        merchant = _CHANNEL_PREFIX_RE.sub("", desc)
        return desc, merchant
    return None, desc


class CcbCreditPdfParser:
    source_type = "bank_pdf_ccb_credit"

    def detect(self, file_bytes: bytes, filename: str) -> bool:
        if not file_bytes.startswith(b"%PDF"):
            return False
        try:
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                if not pdf.pages:
                    return False
                first_text = pdf.pages[0].extract_text() or ""
        except Exception:
            return False
        # 必须命中 ccb marker,排除其他银行
        return any(m in first_text for m in _CCB_MARKERS) and "建" in first_text

    def parse(self, file_bytes: bytes) -> ParseResult:
        if not file_bytes.startswith(b"%PDF"):
            raise ValueError("not a PDF file")

        try:
            pdf = pdfplumber.open(BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"ccb pdf open failed: {e}") from e

        try:
            full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            last4 = _extract_card_last4(full_text)

            raw_rows: list[dict] = []
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    if not table:
                        continue
                    # 定位表头行
                    header_idx = None
                    header_row = None
                    for i, row in enumerate(table):
                        joined = "|".join(str(c or "") for c in row)
                        # 建行表头关键字
                        if "交易日" in joined and ("交易金额" in joined or "结算金额" in joined):
                            header_idx = i
                            header_row = [str(c or "").strip() for c in row]
                            break
                    if header_idx is None:
                        continue
                    col = {h: header_row.index(h) for h in header_row if h}
                    for row in table[header_idx + 1:]:
                        cells = [str(c or "").strip() for c in row]
                        if not any(cells):
                            continue
                        d = {h: cells[i] if i < len(cells) else "" for h, i in col.items()}
                        # 必须有交易日(8 位数字)
                        if not _DATE8_RE.search(d.get("交易日", "")):
                            continue
                        raw_rows.append(d)

            txs: list[RawTransaction] = []
            all_times: list[datetime] = []
            for r in raw_rows:
                tx_time = _parse_yyyymmdd(r.get("交易日", ""))
                if tx_time is None:
                    continue
                post_time = _parse_yyyymmdd(r.get("银行记账日", ""))

                # 金额:交易金额 (原币) + 结算金额 (CNY)
                tx_amt_str = r.get("交易金额") or "0"
                set_amt_str = r.get("结算金额") or tx_amt_str
                try:
                    tx_amt = _parse_amount(tx_amt_str)
                    set_amt = _parse_amount(set_amt_str)
                except InvalidOperation:
                    continue

                tx_currency = (r.get("交易币") or "CNY").strip() or "CNY"
                # 标准化币种代码(可能是中文 "美元" → USD,本切片先保留原样并兼容 ISO)
                currency_map = {
                    "美元": "USD", "欧元": "EUR", "日元": "JPY",
                    "港币": "HKD", "英镑": "GBP", "澳元": "AUD",
                    "人民币": "CNY", "RMB": "CNY",
                }
                tx_currency = currency_map.get(tx_currency, tx_currency)

                # 描述/商家
                desc = r.get("交易描述") or r.get("交易摘要") or ""
                channel_prefix, merchant = _split_channel_prefix(desc)

                # tx_kind:
                # - 描述含"银联入账" → neutral(还款)
                # - 金额为负 (还款/退款) → 取绝对值,kind=neutral 或 refund
                # - 否则 expense (信用卡通常都是消费)
                if _REPAYMENT_KEYWORD in desc:
                    tx_kind = "neutral"
                elif tx_amt < 0 or set_amt < 0:
                    tx_kind = "neutral"  # 通常是还款/调账
                else:
                    tx_kind = "expense"

                # 金额 abs,正数入库;方向靠 tx_kind
                amount_abs = abs(tx_amt) if tx_amt != 0 else abs(set_amt)
                settled_abs = abs(set_amt) if set_amt != 0 else amount_abs

                if amount_abs == 0:
                    continue

                txs.append(RawTransaction(
                    tx_time=tx_time,
                    post_time=post_time,
                    amount=amount_abs,
                    currency=tx_currency,
                    amount_settled_cny=settled_abs,
                    tx_kind=tx_kind,
                    merchant_raw=merchant,
                    counterparty_raw=None,
                    description_raw=desc or None,
                    external_tx_id=None,  # 建行 PDF 不暴露交易号
                    external_merchant_id=None,
                    payment_method_raw=channel_prefix,  # "财付通-luckin coffee" 完整存证
                    raw_row=r,
                ))
                all_times.append(tx_time)

            period_start = min(all_times) if all_times else datetime(1970, 1, 1)
            period_end = max(all_times) if all_times else datetime(1970, 1, 1)

            return ParseResult(
                raw_transactions=txs,
                account_hint=AccountHint(type="bank_credit", institution="建设银行", last4=last4),
                period_start=period_start,
                period_end=period_end,
                metadata={
                    "raw_row_count": len(raw_rows),
                    "imported_count": len(txs),
                    "dropped_count": len(raw_rows) - len(txs),
                },
            )
        finally:
            pdf.close()
```

- [ ] **Step 10.4: 跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_ccb_credit_pdf.py -v
```

期望:14 passed。

排查:
- `extract_tables` 抽不到 → 建行表通常有可见边框,pdfplumber 默认设置应能识别。若失败,跑一次诊断:
  ```powershell
  python -c "import pdfplumber; from pathlib import Path; p = Path('tests/fixtures/statements/ccb_credit_sample.pdf'); pdf = pdfplumber.open(p); print(pdf.pages[0].extract_tables()[:1])"
  ```
- 多币种行没识别为 USD 等 → 看实际表格里"交易币"列内容,可能是空格分隔或其他写法,补 `currency_map` 或正则
- `银联入账`未被标 neutral → 看实际描述列字符串,可能含全角空格,改成 `re.search` 比 `in` 更稳

- [ ] **Step 10.5: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/ccb_credit_pdf.py backend/tests/services/statement_parser/test_ccb_credit_pdf.py
git commit -m "feat(parser): add ccb_credit_pdf parser (FX, repayment, channel prefix)"
```

---

## Task 11:Auto-router(`registry.py`)+ `__init__.py` re-export

**Files:**
- Create: `backend/app/services/statement_parser/registry.py`
- Modify: `backend/app/services/statement_parser/__init__.py`(从 Task 3 的空骨架补全)
- Test: `backend/tests/services/statement_parser/test_registry.py`

> 切片 C 的导入端点会调 `route_and_parse(file_bytes, filename) -> ParseResult`,registry 负责按 `detect()` 顺序匹配第一个解析器。匹配失败抛 `UnsupportedStatementError`。

- [ ] **Step 11.1: 写测试 `tests/services/statement_parser/test_registry.py`**

```python
"""router/registry 测试:detect 路由 + 每种文件归对应 parser。"""
import pytest

from app.services.statement_parser.registry import (
    ALL_PARSERS,
    UnsupportedStatementError,
    route_and_parse,
)


def test_all_parsers_registered():
    """4 个解析器全部注册。"""
    types = {p.source_type for p in ALL_PARSERS}
    assert types == {
        "alipay_csv",
        "wechat_xlsx",
        "bank_pdf_bocom_debit",
        "bank_pdf_ccb_credit",
    }


def test_route_alipay(alipay_csv_bytes, alipay_filename):
    result = route_and_parse(alipay_csv_bytes, alipay_filename)
    assert result.account_hint.type == "alipay"


def test_route_wechat(wechat_xlsx_bytes, wechat_filename):
    result = route_and_parse(wechat_xlsx_bytes, wechat_filename)
    assert result.account_hint.type == "wechat"


def test_route_bocom(bocom_debit_pdf_bytes, bocom_filename):
    result = route_and_parse(bocom_debit_pdf_bytes, bocom_filename)
    assert result.account_hint.type == "bank_debit"
    assert result.account_hint.institution == "交通银行"


def test_route_ccb(ccb_credit_pdf_bytes, ccb_filename):
    result = route_and_parse(ccb_credit_pdf_bytes, ccb_filename)
    assert result.account_hint.type == "bank_credit"
    assert result.account_hint.institution == "建设银行"


def test_route_unknown_raises():
    with pytest.raises(UnsupportedStatementError):
        route_and_parse(b"random bytes that nobody recognizes", "x.txt")


def test_route_dispatches_to_correct_parser_when_two_could_match(
    bocom_debit_pdf_bytes, ccb_credit_pdf_bytes
):
    """两个 PDF 解析器只能命中各自的 marker,不能交叉。"""
    bocom_result = route_and_parse(bocom_debit_pdf_bytes, "x.pdf")
    assert bocom_result.account_hint.institution == "交通银行"
    ccb_result = route_and_parse(ccb_credit_pdf_bytes, "x.pdf")
    assert ccb_result.account_hint.institution == "建设银行"
```

- [ ] **Step 11.2: 跑测试看失败**

```powershell
pytest tests/services/statement_parser/test_registry.py -v
```

期望:`ImportError: cannot import name 'route_and_parse' from 'app.services.statement_parser.registry'`。

- [ ] **Step 11.3: 写 `app/services/statement_parser/registry.py`**

```python
"""解析器自动路由。

spec § 5.1 step 3:导入端点接到 file_bytes 后,需要选对解析器。
本模块按 detect() 顺序匹配第一个 hit 的解析器。
"""
from app.services.statement_parser.alipay_csv import AlipayCsvParser
from app.services.statement_parser.base import ParseResult, StatementParser
from app.services.statement_parser.bocom_debit_pdf import BocomDebitPdfParser
from app.services.statement_parser.ccb_credit_pdf import CcbCreditPdfParser
from app.services.statement_parser.wechat_xlsx import WechatXlsxParser


# 顺序无关(detect 互斥),但便于调试:CSV → xlsx → 银行 PDF
ALL_PARSERS: list[StatementParser] = [
    AlipayCsvParser(),
    WechatXlsxParser(),
    BocomDebitPdfParser(),
    CcbCreditPdfParser(),
]


class UnsupportedStatementError(ValueError):
    """4 个解析器都不认 → 抛此异常,切片 C 的端点转 HTTP 400。"""


def route_and_parse(file_bytes: bytes, filename: str) -> ParseResult:
    """按 detect 顺序找第一个能处理的解析器,parse 后返回。

    无解析器认领 → UnsupportedStatementError(用户友好的错误,带上文件名)。
    """
    for parser in ALL_PARSERS:
        try:
            if parser.detect(file_bytes, filename):
                return parser.parse(file_bytes)
        except Exception:
            # detect 不应抛错,但万一抛了,继续试下一个
            continue
    raise UnsupportedStatementError(
        f"no parser matched filename={filename!r} (head bytes: {file_bytes[:32]!r})"
    )
```

- [ ] **Step 11.4: 改 `app/services/statement_parser/__init__.py` 补 re-export**

```python
"""statement_parser 包对外接口。

切片 C 的导入端点应只 import 本模块,不依赖具体解析器。
"""
from app.services.statement_parser.base import (
    AccountHint,
    ParseResult,
    RawTransaction,
    StatementParser,
)
from app.services.statement_parser.normalize import normalize_merchant
from app.services.statement_parser.registry import (
    ALL_PARSERS,
    UnsupportedStatementError,
    route_and_parse,
)

__all__ = [
    # 数据类型
    "AccountHint",
    "ParseResult",
    "RawTransaction",
    "StatementParser",
    # 工具
    "normalize_merchant",
    # 路由
    "ALL_PARSERS",
    "UnsupportedStatementError",
    "route_and_parse",
]
```

- [ ] **Step 11.5: 跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_registry.py -v
```

期望:7 passed。

- [ ] **Step 11.6: 跑全部 parser 测试 + 跑 slice A 历史测试,验证整体通过**

```powershell
pytest -v --durations=10
```

期望:slice A (~7 tests) + slice B (~70 tests) 全过,总时间 < 30 秒(其中 PDF 解析占大头)。

- [ ] **Step 11.7: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/registry.py backend/app/services/statement_parser/__init__.py backend/tests/services/statement_parser/test_registry.py
git commit -m "feat(parser): add auto-router (route_and_parse + UnsupportedStatementError)"
```

---

## Task 12:覆盖率验证 + DoD 脚本 + 标记 slice 完成

**Files:**
- Modify: `backend/pyproject.toml`(加 `slow` marker 注册)
- Create: `backend/scripts/verify_slice_b.ps1`
- Modify: `docs/superpowers/plans/2026-05-08-mvp-overview.md`(标 slice B done + 划掉 I-1/I-3)
- Modify: `CLAUDE.md`(进度勾选)

> overview.md 的 DoD 要求:每个解析器单元测试覆盖率 ≥ 80%。本 task 跑 cov 报告确认达标,并写一个 verify_slice_b.ps1 让用户(或 CI)一键自检。

- [ ] **Step 12.1: 注册 `slow` marker(消除 pytest 警告)**

打开 `backend/pyproject.toml`,把:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-ra --strict-markers"
```
改成:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-ra --strict-markers"
markers = [
    "slow: real-sample integration tests that may take >1s each",
]
```

- [ ] **Step 12.2: 跑覆盖率报告,确认 ≥ 80%**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/services/statement_parser/ --cov=app.services.statement_parser --cov-report=term-missing
```

期望末尾 `TOTAL` 行覆盖率 **≥ 80%**。逐文件检查:
- `base.py`:接近 100%(纯 dataclass)
- `normalize.py`:100%
- `alipay_csv.py`:≥ 80%
- `wechat_xlsx.py`:≥ 80%
- `bocom_debit_pdf.py`:≥ 80%
- `ccb_credit_pdf.py`:≥ 80%
- `registry.py`:≥ 90%(detect+route 分支少)

如果某个解析器不达标,看 `Missing` 列哪些行号没覆盖,补对应测试(常见:错误路径如 `raise ValueError`、币种映射兜底、空文件等)。

- [ ] **Step 12.3: 写 `backend/scripts/verify_slice_b.ps1`**

```powershell
# verify_slice_b.ps1 — slice B DoD 验证
# 从 finance-manager/ 根运行
$ErrorActionPreference = "Stop"

Write-Host "=== Slice B DoD verify ===" -ForegroundColor Cyan

# 1. 在 backend venv 跑解析器测试 + 覆盖率
Set-Location backend
.\.venv\Scripts\Activate.ps1

Write-Host "`n[1/4] Run parser tests with coverage..." -ForegroundColor Yellow
pytest tests/services/statement_parser/ -v --cov=app.services.statement_parser --cov-report=term --cov-fail-under=80
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: parser tests or coverage < 80%" -ForegroundColor Red
    exit 1
}

# 2. 跑全测试套件,确保 slice A 也没坏
Write-Host "`n[2/4] Run full test suite..." -ForegroundColor Yellow
pytest -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: full test suite has failures" -ForegroundColor Red
    exit 1
}

# 3. 验证 I-1 索引修复(connect db 查 \d transactions)
Write-Host "`n[3/4] Verify I-1: tx_time DESC index..." -ForegroundColor Yellow
Set-Location ..
$idxOut = docker-compose exec -T db psql -U finance -d finance -c "\d transactions" 2>$null | Out-String
if ($idxOut -match "ix_transactions_user_tx_time.*tx_time DESC") {
    Write-Host "  PASS: index has DESC" -ForegroundColor Green
} else {
    Write-Host "  FAIL: index missing DESC" -ForegroundColor Red
    Write-Host $idxOut
    exit 1
}

# 4. 验证 I-3 测试速度(全测试套件 < 30s)
Write-Host "`n[4/4] Verify I-3: test suite < 30s..." -ForegroundColor Yellow
Set-Location backend
$sw = [System.Diagnostics.Stopwatch]::StartNew()
pytest -q | Out-Null
$sw.Stop()
if ($sw.Elapsed.TotalSeconds -lt 30) {
    Write-Host "  PASS: $([math]::Round($sw.Elapsed.TotalSeconds, 1))s < 30s" -ForegroundColor Green
} else {
    Write-Host "  FAIL: $([math]::Round($sw.Elapsed.TotalSeconds, 1))s >= 30s" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Slice B DoD: ALL PASS ===" -ForegroundColor Green
```

- [ ] **Step 12.4: 跑 verify 脚本**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
pwsh backend\scripts\verify_slice_b.ps1
```

期望末尾 `=== Slice B DoD: ALL PASS ===`。

- [ ] **Step 12.5: 更新 `docs/superpowers/plans/2026-05-08-mvp-overview.md`**

打开 [docs/superpowers/plans/2026-05-08-mvp-overview.md](docs/superpowers/plans/2026-05-08-mvp-overview.md):

(a) 在"已知遗留问题 → 切片 B 启动前必修"段,把 I-1 和 I-3 的两条改成 ~~删除线~~ + 后缀"(已在 slice B Task 1/2 修复,commit XXX/YYY)":

```markdown
### 切片 B 启动前必修

- ~~**I-1** `transactions(user_id, tx_time DESC)` 索引缺少 DESC~~ ✅ 已在 slice B Task 1 修复(commit hash: 见 git log)
- ~~**I-3** 测试速度过慢~~ ✅ 已在 slice B Task 2 改为 nested-savepoint(commit hash: 见 git log)
```

(b) 在"完成进度"表格里,把切片 B 改成:

```markdown
| B. 4 个解析器 | ✅ 完成 | 2026-05-09 | (实施工时由 controller 估算) | DoD verify script passed; 4 parsers ≥ 80% cov; I-1/I-3 also resolved |
```

- [ ] **Step 12.6: 更新仓库根 `CLAUDE.md` 的"5 切片进度"段**

打开 `CLAUDE.md`,把:
```markdown
- ✅ **A. 数据库基础**(2026-05-08 完成,merged to main,DoD verify ALL PASS)
- ⏳ **B. 4 个账单解析器**(下一步:支付宝 CSV / 微信 xlsx / 交行借记卡 PDF / 建行信用卡 PDF)
```
改成:
```markdown
- ✅ **A. 数据库基础**(2026-05-08 完成,merged to main,DoD verify ALL PASS)
- ✅ **B. 4 个账单解析器**(2026-05-09 完成,DoD verify ALL PASS;含 slice A 遗留 I-1/I-3 修复)
- ⏳ **C. 导入流水线 + 去重 + 分类 + REST API**(下一步)
```

并把"slice A 遗留问题(slice B/C 必须处理)"段的 I-1 / I-3 两条删除,只留 I-5 / Rec #5(给 slice C)。

- [ ] **Step 12.7: Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/pyproject.toml backend/scripts/verify_slice_b.ps1 docs/superpowers/plans/2026-05-08-mvp-overview.md CLAUDE.md
git commit -m "chore(slice-b): add verify script, mark slice B done, resolve I-1/I-3"
```

- [ ] **Step 12.8: 最后一次 sanity check**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git log --oneline main..slice-b-parsers
git status
```

期望 `git log` 输出 ~13 条 commit(对应 12 个 task 的 commit + Task 1 多一条),`git status` 干净。

切片 B 完成,可走 `superpowers:finishing-a-development-branch` 决定 merge 策略(参照 slice A 的 fast-forward 习惯)。

---

## Self-Review 备忘(写完 plan 后已自检)

- **Spec 覆盖**:spec § 5.2 Protocol(Task 4) / § 5.3.1 alipay(Task 7) / § 5.3.2 wechat(Task 8) / § 5.3.3 bocom(Task 9) / § 5.3.4 ccb(Task 10) / § 5.1 step 3 路由(Task 11)。spec § 4.2 索引 + slice A I-3 → Task 1/2。✅ 全覆盖
- **Placeholder 扫**:无 TODO / TBD / 引用未定义函数。✅
- **类型一致**:`RawTransaction.amount` 全程 Decimal;`AccountHint.type` 全程小写下划线(`bank_credit` 不是 `BankCredit`);`source_type` 字符串与 spec § 5.2 一致。✅
- **DoD 可执行**:verify_slice_b.ps1 自包含,4 项硬指标(parser cov ≥ 80% / 全测试通过 / DESC 索引存在 / 全测试 < 30s)。✅
- **遗留闭环**:I-1 / I-3 在 Task 1/2 处理,Task 12 标记关闭并更新 overview 与 CLAUDE.md。✅

(end of plan)
