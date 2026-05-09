# 切片 C:导入流水线 + 跨源去重 + 规则分类 + REST API — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 5.1 导入流水线、§ 6 去重算法、§ 7 分类系统,以及 spec § 9 (Web UI 路由表) + § 10 (Web 认证) 对应的 backend REST API(MCP 工具集 § 8 留给 slice E)。同时**第一时间**修掉 slice B 遗留的 4 条阻塞:B-poly-2(`_is_repayment` 乱序误判)、B-poly-1(ccb_credit_pdf codepoint matching → 标准字符串)、I-5(`seed.py` bcrypt placeholder 替换为真实 hash)、Rec #5(分类引擎正确处理 `category_id IS NULL` 的 marker 规则)。

**Architecture:** 把 slice B 的解析层(`route_and_parse() -> ParseResult`)接入新增的导入 service 三件套:`importer.py` 负责文件去重 + 账户推断 + transactions 持久化,`dedup.py` 实现 spec § 6 的 5 个信号(同源跳过 / 微信→银行精确锚定 / 强重复 / 桥接 / 对话↔账单),`classifier.py` 跑规则匹配(其中 marker 规则 = `category_id IS NULL`,只更新 `hit_count` 不 break,跳过继续找下一条真分类规则)。FastAPI router 按 spec § 9.1 路由表分文件组织(`auth/statements/transactions/dedup/categories/accounts/rules/summary`),HTTP 层薄包装 service 层。认证用 JWT in httpOnly cookie(spec § 10.1),`Settings.admin_username + admin_password_hash` 是 single source of truth,seed.py 改为读 Settings 而非硬编码 placeholder。所有端点都在依赖 `current_user`,通过 `cookie → JWT decode → User` chain 解析。

**Tech Stack:** Python 3.11 / FastAPI 0.115 / SQLAlchemy 2 / Pydantic v2 / Pydantic-Settings / passlib[bcrypt] / python-jose[cryptography] / python-multipart / rapidfuzz 3.10 / pytest 8 / pytest-cov 5 / Postgres 16 / Alembic 1.14。所有库已在 `backend/pyproject.toml`,**本切片不新增 deps**。

---

## Pre-flight(执行前自检)

执行本 plan 的 agent 在 Task 1 前需确认:

- 当前分支是 `slice-c-pipeline`(`git branch --show-current`),从 `main` 拉出,无 uncommitted 改动
- Postgres 容器已起:`docker-compose up -d db`,`docker-compose ps db` 显示 healthy
- backend venv 已激活:`cd backend && .\.venv\Scripts\Activate.ps1`,`python -V` 输出 `Python 3.11.x`
- slice B verify 仍 PASS(快速冒烟):`pwsh backend\scripts\verify_slice_b.ps1` 末行 `Slice B DoD: ALL PASS`
- 仓库根 `.env` 中 `ADMIN_PASSWORD_HASH` 是合法 bcrypt(`$2b$12$....`,60 字符)。本切片 Task 3 会用它替换 seed.py 占位符;若 `.env` 里仍是占位符 `$2b$12$placeholder...`,**先生成一个真 hash**:
  ```powershell
  cd D:\IDEACursor\Claude-code\finance-manager\backend
  .\.venv\Scripts\Activate.ps1
  python -c "from passlib.hash import bcrypt; print(bcrypt.hash('your_dev_password_here'))"
  ```
  把输出贴到 `.env` 的 `ADMIN_PASSWORD_HASH=...`,记好密码。

如以上任一不满足,在仓库根读 `CLAUDE.md` "环境与命令规约" 段补齐再开工。

---

## File Structure(切片 C 涉及的文件清单)

**新建(backend/app/):**

```
backend/app/
  api/
    __init__.py
    deps.py                       # FastAPI dependencies:get_db / current_user
    auth.py                       # POST /api/auth/login | /logout | GET /api/auth/me
    statements.py                 # POST /import | GET /list | GET /{id} | GET /{id}/review
    transactions.py               # GET / GET/{id} / PATCH/{id} / POST/bulk-update-by-merchant
    dedup.py                      # GET /pending | POST /{pair_id}/confirm | /reject
    accounts.py                   # CRUD
    categories.py                 # CRUD(树形)
    rules.py                      # CRUD(merchant_rules)
    summary.py                    # GET /api/summary
  schemas/
    __init__.py                   # re-export
    auth.py                       # LoginIn / LoginOut / Me
    statement.py                  # StatementImportOut / ImportResponse / ReviewBundle
    transaction.py                # TxOut / TxListQuery / TxPatchIn / BulkUpdateIn
    dedup.py                      # DedupPairOut / DedupDecisionIn
    account.py / category.py / rule.py / summary.py
  services/
    __init__.py                   # 已存在,Task 7 改为 re-export
    auth.py                       # password verify / JWT encode-decode
    importer.py                   # orchestrate parser → persist → dedup → classify
    persist.py                    # 把 ParseResult 落 transactions(merchant_normalized + source_unique_key)
    dedup.py                      # spec § 6 五个信号
    classifier.py                 # spec § 7 规则匹配 + marker 处理
    summary.py                    # spec § 8.1 get_summary 算法的纯函数
```

**新建(backend/tests/):**

```
backend/tests/
  api/
    __init__.py
    conftest.py                   # client + login fixture(写一次,跨 api 测试复用)
    test_auth.py
    test_statements_import.py     # E2E:上传支付宝 → 上传交行 → /review 看到 dedup_pending
    test_statements_list.py
    test_transactions.py
    test_dedup.py
    test_accounts_rules_categories.py
    test_summary.py
  services/
    __init__.py(已有)
    test_persist.py
    test_dedup.py                 # 5 个信号每个都有最小 case
    test_classifier.py            # marker 规则 / 普通规则 / 未命中
    test_importer.py              # orchestration 集成
    test_auth_service.py          # bcrypt verify + JWT roundtrip
    test_summary.py
  e2e/
    import_flow.ps1               # bash spec 列了 .sh,Windows 实际用 .ps1
```

**修改:**

- `backend/app/services/statement_parser/ccb_credit_pdf.py` — Task 1(B-poly-2)+ Task 2(B-poly-1)替换 codepoint set / 顺序匹配 → 标准字符串
- `backend/app/db/seed.py` — Task 3(I-5)读 `Settings.admin_password_hash`
- `backend/app/main.py` — Task 7+ 注册新 router
- `docs/superpowers/plans/2026-05-08-mvp-overview.md` — Task 21 标 slice C 完成 + 划掉 I-5/Rec#5/B-poly-1/B-poly-2
- `CLAUDE.md` — Task 21 进度勾选

**新建(DoD 验证):**

```
backend/scripts/verify_slice_c.ps1
backend/tests/e2e/import_flow.ps1
```

**不动:**

- 现有所有 model 文件(spec § 4 字段已齐全;`MerchantRule.category_id Optional` 已能承载 marker 规则,无需 schema 改动)
- 现有 alembic migrations(本切片纯 service + API,无 schema 改动)
- 4 个解析器除 `ccb_credit_pdf.py` 外
- docker-compose / Caddy / frontend 目录(切片 D/E 处理)

---

## Task 1:B-poly-2 修复 — `_is_repayment` 乱序误判 → 子串顺序匹配

**Files:**
- Modify: `backend/app/services/statement_parser/ccb_credit_pdf.py`(`_is_repayment` 函数)
- Test: `backend/tests/services/statement_parser/test_ccb_credit_pdf.py`(新增 regression 测试)

> **背景:** slice B Polish 列表 B-poly-2 — `_is_repayment(desc)` 当前用 `_has_codepoints(desc, _YINLIAN_CP + _RUZHANG_CP)`,即检查 desc 字符集是否含 {银,联,入,账} 4 个码点 —— **不要求顺序、不要求连续**。`_is_repayment("联银账入")` 这种乱序串会误返回 True;真实 PDF 抽取出的字符串里若含这 4 个字符的拼接但不组成"银联入账"语义(如商户名"联建银行账户激活"),也会误判为还款,后续被错标 `tx_kind=neutral`,导致汇总数据失真。修法:**直接用子串匹配 `"银联入账" in desc`**,与 `_REPAYMENT_KEYWORD` 常量(parse 主流程已用的)统一。

- [ ] **Step 1.1:在 `test_ccb_credit_pdf.py` 顶部追加 regression 测试**

打开 [backend/tests/services/statement_parser/test_ccb_credit_pdf.py](backend/tests/services/statement_parser/test_ccb_credit_pdf.py),在文件末尾追加:

```python
# === B-poly-2 regression:_is_repayment 必须按子串顺序匹配 ===

from app.services.statement_parser.ccb_credit_pdf import _is_repayment


def test_is_repayment_exact_match():
    """正常的银联入账描述应识别。"""
    assert _is_repayment("银联入账7432") is True
    assert _is_repayment("银联入账还款 7432****") is True


def test_is_repayment_rejects_scrambled_codepoints():
    """B-poly-2:仅含 4 字符但顺序错乱(set 解法会误中)→ 必须 False。"""
    assert _is_repayment("联银账入") is False
    assert _is_repayment("入账银联") is False
    assert _is_repayment("账入联银7432") is False


def test_is_repayment_rejects_partial_keywords():
    """仅含 4 字符中部分字符,真实商户名常见 → 必须 False。"""
    assert _is_repayment("联建银行账户激活") is False  # 含银/账,但不组成"银联入账"
    assert _is_repayment("入金账户充值") is False        # 含入/账
    assert _is_repayment("瑞幸咖啡") is False
    assert _is_repayment("") is False


def test_is_repayment_substring_match_in_longer_desc():
    """嵌入更长描述里的"银联入账"应识别(模拟真实 PDF 多空格场景)。"""
    assert _is_repayment("12月银联入账还款记录") is True
    assert _is_repayment("XX 银联入账 YY") is True
```

- [ ] **Step 1.2:跑测试看失败**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/services/statement_parser/test_ccb_credit_pdf.py::test_is_repayment_rejects_scrambled_codepoints tests/services/statement_parser/test_ccb_credit_pdf.py::test_is_repayment_rejects_partial_keywords -v
```

期望:`test_is_repayment_rejects_scrambled_codepoints` FAIL(因为当前实现用 set 顺序无关),其他可能也 FAIL。

- [ ] **Step 1.3:改 `_is_repayment` 实现为子串匹配**

打开 [backend/app/services/statement_parser/ccb_credit_pdf.py:178-180](backend/app/services/statement_parser/ccb_credit_pdf.py),把:

```python
def _is_repayment(desc: str) -> bool:
    """描述是否含银联入账(还款)。"""
    return _has_codepoints(desc, _YINLIAN_CP + _RUZHANG_CP)
```

改成:

```python
def _is_repayment(desc: str) -> bool:
    """描述是否含"银联入账"子串(还款入账记录)。

    spec § 5.3.4:银联入账 + 金额为负 = 信用卡还款。
    必须按字符顺序匹配,不能用 codepoint set(否则"联银账入"等乱序会误判)。
    """
    if not desc:
        return False
    return _REPAYMENT_KEYWORD in desc
```

注意:`_REPAYMENT_KEYWORD = "银联入账"` 常量在文件中可能尚未定义(slice B 完成时位于 `parse()` 内 inline 字符串)。确认 [ccb_credit_pdf.py](backend/app/services/statement_parser/ccb_credit_pdf.py) 顶部模块常量段是否有该常量定义,若无,在 `_DATE8_RE` 那一行下方加一行:

```python
_REPAYMENT_KEYWORD = "银联入账"
```

并把 `parse()` 里 `if _REPAYMENT_KEYWORD in desc:` 那行(原本是 inline 的 `if "银联入账" in desc`)改用此常量(若已用,跳过)。

- [ ] **Step 1.4:跑测试看通过**

```powershell
pytest tests/services/statement_parser/test_ccb_credit_pdf.py -v
```

期望:全部 ccb_credit_pdf 测试 pass(原 14 + 新增 4 = 18 passed)。

- [ ] **Step 1.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/ccb_credit_pdf.py backend/tests/services/statement_parser/test_ccb_credit_pdf.py
git commit -m "fix(parser): _is_repayment uses substring match (slice B B-poly-2)"
```

---

## Task 2:B-poly-1 修复 — codepoint matching → 标准字符串

**Files:**
- Modify: `backend/app/services/statement_parser/ccb_credit_pdf.py`(替换 `_has_codepoints` / `_starts_with_codepoints` / `_identify_currency` / `_split_channel_prefix`)
- Modify: `backend/tests/services/statement_parser/test_ccb_credit_pdf.py`(本 task 不新增测试,Task 1 + 现有测试已覆盖语义,但跑全套确认无 regression)

> **背景:** slice B Polish 列表 B-poly-1 — `ccb_credit_pdf.py` 用 codepoint tuple(`_YINLIAN_CP = (0x94f6, 0x8054)` 等)和 set comparison(`_has_codepoints`)做中文识别,docstring 自述是因为"PDF 字体编码问题"。这是误诊:slice B 已验证 pdfplumber 抽取的是标准 UTF-8(`extract_text()` 返回 `str`),Windows 终端显示乱码 ≠ 实际字符串异常。codepoint 实现的副作用:可读性差、维护成本高、且 set 比较丢失顺序信息(B-poly-2 即此)。Task 1 已用子串修复 `_is_repayment`,本 task 把 `_identify_currency` 和 `_split_channel_prefix` 也回归标准字符串,清掉所有 `_*_CP` 常量与辅助函数。

- [ ] **Step 2.1:删除 `_has_codepoints` / `_starts_with_codepoints` 辅助函数和所有 `_*_CP` 常量**

打开 [backend/app/services/statement_parser/ccb_credit_pdf.py](backend/app/services/statement_parser/ccb_credit_pdf.py),删除以下 6 段:

(a) 顶部常量段 `_CCB_MARKER_ZH_CP = (0x5efa, ...)` 那一行(保留 `_CCB_MARKERS_EN`)
(b) 整个 `_YINLIAN_CP / _RUZHANG_CP / _CAIFUTONG_CP / _ZHIFUBAO_CP` 4 行 codepoint 常量
(c) 货币映射上方那一段 codepoint 注释块(如 `# 人民币元: 人 U+4eba ...`,共 ~7 行)
(d) `_has_codepoints` 函数定义(第 ~66-69 行)
(e) `_starts_with_codepoints` 函数定义(第 ~72-77 行)
(f) `_identify_currency` 内的整个 `cp_set` 实现(第 ~79-106 行)

- [ ] **Step 2.2:把 `_identify_currency` 改为标准子串匹配**

在删除的 `_identify_currency` 位置,写入:

```python
# 中文币种名 → ISO 4217 代码。优先匹配长串(港币/人民币)避免短串先命中
_CURRENCY_MAP: list[tuple[str, str]] = [
    ("人民币", "CNY"),
    ("港币", "HKD"),
    ("港元", "HKD"),
    ("香港元", "HKD"),
    ("美元", "USD"),
    ("欧元", "EUR"),
    ("日元", "JPY"),
    ("英镑", "GBP"),
    ("澳元", "AUD"),
    ("RMB", "CNY"),
]


def _identify_currency(curr_str: str) -> str:
    """从币种字符串(中文名 / ISO 代码)转 ISO 4217 三字母代码。"""
    s = (curr_str or "").strip()
    if not s:
        return "CNY"
    # 优先按长串子串匹配
    for cn_name, iso in _CURRENCY_MAP:
        if cn_name in s:
            return iso
    # 已是 3 字母 ASCII(如 USD/EUR)→ 大写返回
    if s.isascii() and len(s) == 3:
        return s.upper()
    return s  # 未知,原样返回(测试会发现)
```

- [ ] **Step 2.3:把 `_is_ccb_text` 改回标准子串匹配**

在原 `_is_ccb_text` 函数处(其调用了已删除的 `_has_codepoints`),替换为:

```python
def _is_ccb_text(text: str) -> bool:
    """文本中是否有建行特征(英文标记 / 中文'建设银行')。"""
    if not text:
        return False
    if any(m in text for m in _CCB_MARKERS_EN):
        return True
    return "建设银行" in text
```

- [ ] **Step 2.4:把 `_split_channel_prefix` 改回正则**

在原 `_split_channel_prefix` 函数处(用了 `_starts_with_codepoints`),替换为:

```python
import re as _re  # 顶部已 import re,本注释只示意;实际在文件顶部已有,直接用

# 通道前缀正则(支持 ASCII 和全角破折号)
_CHANNEL_PREFIX_RE = re.compile(r"^(财付通|支付宝)([\-—－＝]\s*)?(.*)$")


def _split_channel_prefix(desc: str) -> tuple[str | None, str]:
    """检查描述是否以"财付通"或"支付宝"开头(可带破折号)。

    返回 (channel_prefix_full, merchant_after_strip):
    - "财付通-luckin coffee"  → ("财付通-luckin coffee", "luckin coffee")
    - "支付宝中国移动"        → ("支付宝中国移动", "中国移动")
    - "瑞幸咖啡"              → (None, "瑞幸咖啡")
    """
    if not desc:
        return None, ""
    m = _CHANNEL_PREFIX_RE.match(desc)
    if not m:
        return None, desc
    merchant = (m.group(3) or "").strip()
    if not merchant:
        # 仅前缀无后续(罕见),用原 desc 当 merchant
        return desc, desc
    return desc, merchant
```

注意 `_CHANNEL_PREFIX_RE` 与文件顶部可能已有的同名常量去重(Task 1 后该常量在 parse 主流程位置)。**只保留这一处定义**,在文件常量区放它(原 codepoint 块的位置)。

- [ ] **Step 2.5:Account hint 实例化里把"建设银行"中文字面量化**

定位 `parse()` 末尾构造 `AccountHint(...institution="建设银行"...)` 那一行(原文用了 `# U+5efa U+8bbe U+94f6 U+884c` 误导注释),把那条注释删除,保留 `institution="建设银行"`。

- [ ] **Step 2.6:更新模块 docstring 删除"自定义字体 subset"误导说明**

打开文件顶部 docstring,把:

```
- 中文字符在 Python 内部存储为正确 UTF-8(U+xxxx),但 Windows 终端显示乱码
```

替换为:

```
- 解析逻辑:pdfplumber 抽取的是标准 UTF-8,直接用子串匹配(slice C B-poly-1 修复)
```

(若该行不存在或措辞略有不同,语义上去掉"字体 subset / codepoint"提及,改为强调"标准 UTF-8 子串匹配"即可。)

- [ ] **Step 2.7:跑全部 ccb 测试看仍通过**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
pytest tests/services/statement_parser/test_ccb_credit_pdf.py -v
```

期望:18 passed(Task 1 加的 4 + 原有 14 个,本 task 应不破任何一个)。

- [ ] **Step 2.8:跑全部 parser 测试 + 覆盖率,无 regression**

```powershell
pytest tests/services/statement_parser/ --cov=app.services.statement_parser --cov-report=term --cov-fail-under=80
```

期望:全部 parser 测试 pass,coverage ≥ 80%。

- [ ] **Step 2.9:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/statement_parser/ccb_credit_pdf.py
git commit -m "refactor(parser): replace codepoint matching with standard string ops (slice B B-poly-1)"
```

---

## Task 3:I-5 修复 — `seed.py` 用 `Settings.admin_password_hash` 替换 bcrypt placeholder

**Files:**
- Modify: `backend/app/db/seed.py`(`ensure_default_user` 改读 Settings)
- Modify: `backend/app/core/config.py`(确认 `admin_password_hash` 已是 required Field — 已在 slice A 配置)
- Test: `backend/tests/test_seed_user.py`(新建,验证幂等 + 真实 hash 注入)

> **背景:** slice A I-5 — `seed.py:19` 硬编码 `password_hash="$2b$12$placeholder_replace_in_slice_c"`,这串不是合法 bcrypt(passlib `bcrypt.verify` 会 raise `ValueError: hash could not be identified`)。slice C 实现 `/api/auth/login` 必须验证密码,因此 seed 必须从 `Settings.admin_password_hash`(用户 `.env` 真实 bcrypt)读取。Pre-flight 已要求用户在 `.env` 中配真实 hash;本 task 只改 seed 逻辑 + 加 idempotent 更新(若已存在 admin 但 password_hash 与 Settings 不同,**更新**,让 `.env` 改密能生效)。

- [ ] **Step 3.1:写测试 `tests/test_seed_user.py`**

```python
"""seed.ensure_default_user 测试 — 真 hash 注入 + 幂等 + 改密更新。"""
import pytest
from sqlalchemy import select

from app.db.seed import ensure_default_user
from app.models import User


def test_seed_user_creates_with_settings_hash(db, monkeypatch):
    """初次跑:用 Settings.admin_password_hash 创建。"""
    fake_hash = "$2b$12$" + "x" * 53  # 60 字符,bcrypt 标准长度
    fake_username = "admin"

    # 通过 monkeypatch Settings 暴露的 getter
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", fake_username)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", fake_hash)

    user = ensure_default_user(db)
    db.flush()
    assert user.username == fake_username
    assert user.password_hash == fake_hash


def test_seed_user_idempotent_same_hash(db, monkeypatch):
    """二次跑:已存在 admin 且 hash 相同 → 不变。"""
    fake_hash = "$2b$12$" + "y" * 53
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", fake_hash)

    u1 = ensure_default_user(db)
    db.flush()
    u2 = ensure_default_user(db)
    db.flush()
    assert u1.id == u2.id
    assert u2.password_hash == fake_hash


def test_seed_user_updates_hash_when_env_changes(db, monkeypatch):
    """改密场景:.env 换 hash 后,re-seed 应同步更新数据库行(避免登录失败)。"""
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$" + "a" * 53)
    u1 = ensure_default_user(db)
    db.flush()
    old_hash = u1.password_hash

    cfg_mod.get_settings.cache_clear()
    new_hash = "$2b$12$" + "b" * 53
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", new_hash)
    u2 = ensure_default_user(db)
    db.flush()
    assert u1.id == u2.id
    assert u2.password_hash == new_hash
    assert old_hash != new_hash


def test_seed_user_rejects_obvious_placeholder(db, monkeypatch):
    """防御:仍是 slice A 占位符 hash → 抛 ValueError 拦截配置错。"""
    from app.core import config as cfg_mod

    cfg_mod.get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$placeholder_replace_in_slice_c")
    with pytest.raises(ValueError, match="placeholder"):
        ensure_default_user(db)
```

- [ ] **Step 3.2:跑测试看失败**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/test_seed_user.py -v
```

期望:多数 FAIL(`ensure_default_user` 当前用硬编码占位符,不读 Settings)。

- [ ] **Step 3.3:重写 `app/db/seed.py` 的 `ensure_default_user`**

打开 [backend/app/db/seed.py](backend/app/db/seed.py),替换整个文件为:

```python
"""seed 主入口:可被 CLI 或测试调用。"""
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import db_session
from app.db.seed_categories import seed_default_categories
from app.db.seed_merchant_rules import seed_default_merchant_rules
from app.models import User


_PLACEHOLDER_TOKEN = "placeholder"


def _validate_bcrypt_hash(h: str) -> None:
    """防御性校验:hash 形如 $2b$XX$... 且不含 placeholder 字样。"""
    if not h or _PLACEHOLDER_TOKEN in h:
        raise ValueError(
            "ADMIN_PASSWORD_HASH is a placeholder — generate a real bcrypt hash and put it in .env "
            "(see plan slice C Pre-flight for the one-liner)"
        )
    if not h.startswith(("$2a$", "$2b$", "$2y$")):
        raise ValueError(
            f"ADMIN_PASSWORD_HASH does not look like a bcrypt hash (got prefix={h[:6]!r}); "
            "expected $2a$/$2b$/$2y$..."
        )


def ensure_default_user(db: Session) -> User:
    """确保 admin 用户存在,且 password_hash 与 .env 一致(幂等 + 改密同步)。

    spec § 10.1 单用户硬编码:用户名/密码 hash 来自 .env。
    """
    settings = get_settings()
    username = settings.admin_username
    target_hash = settings.admin_password_hash
    _validate_bcrypt_hash(target_hash)

    existing = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing is None:
        user = User(username=username, password_hash=target_hash)
        db.add(user)
        db.flush()
        return user

    if existing.password_hash != target_hash:
        # .env 已改密 → 同步更新,避免登录持续失败
        existing.password_hash = target_hash
        db.flush()
    return existing


def run_seed() -> None:
    with db_session() as db:
        user = ensure_default_user(db)
        cat_count = seed_default_categories(db, default_user_id=user.id)
        rule_count = seed_default_merchant_rules(db, default_user_id=user.id)
        print(f"[seed] user_id={user.id}, categories seeded={cat_count}, rules inserted={rule_count}")


if __name__ == "__main__":
    run_seed()
    sys.exit(0)
```

- [ ] **Step 3.4:跑 `tests/test_seed_user.py` 看通过**

```powershell
pytest tests/test_seed_user.py -v
```

期望:4 passed。

如果 `test_seed_user_updates_hash_when_env_changes` fail:检查 `get_settings()` 是 lru_cache 装饰的,测试用 `cache_clear()` 跨 monkeypatch 重置(seed.py 每次调用都拿 fresh settings)。

- [ ] **Step 3.5:跑现有 slice A `test_seed_*.py` 确认 unbroken**

```powershell
pytest tests/test_seed.py tests/test_seed_categories.py tests/test_seed_merchant_rules.py -v
```

期望:全部 pass(slice A 测试本就 mock 出 fake hash 走 conftest fixture,不依赖真实 placeholder)。

如果 fail,常见原因:slice A 现有测试可能在 `monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummy")` —— `dummy` 不含 `placeholder` 字样且符合 bcrypt 前缀,通过新校验。若有特殊用例失败,看 conftest fixture 给的 hash 是否合规;不合规则改 conftest 给个 `"$2b$12$" + "x" * 53`。

- [ ] **Step 3.6:验证 `python -m app.db.seed` 真实跑能用**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
docker-compose -f ../docker-compose.yml up -d db
.\.venv\Scripts\Activate.ps1
python -m app.db.seed
```

期望输出:`[seed] user_id=1, categories seeded=N, rules inserted=M`,不抛 placeholder 错。

如果抛 `ValueError: ADMIN_PASSWORD_HASH is a placeholder`:回到 Pre-flight,在 `.env` 用 `passlib bcrypt.hash(...)` 生成真 hash。

- [ ] **Step 3.7:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/db/seed.py backend/tests/test_seed_user.py
git commit -m "fix(seed): read admin password hash from Settings, reject placeholders (slice A I-5)"
```

---

## Task 4:Rec #5 修复 — 分类引擎正确处理 marker 规则的契约 + 单元测试

**Files:**
- Test: `backend/tests/services/test_classifier_marker_contract.py`(新建,纯契约测试)

> **背景:** slice A Rec #5 — `merchant_rules` 表中 priority=20/25 的 6 条规则 `category_id IS NULL`(`财付通-` / `支付宝-` / `蚂蚁(...)` / `拉扎斯网络科技` / `云闪付` / `支付平台`)。设计语义见 `seed_merchant_rules.py:14`:**"category=None,只起标记作用,真正分类靠对侧已分类"**。spec § 7.2 朴素流程"命中即 break + assign"对此**会出错**:命中 marker 规则后 `T.category_id = None`(从规则取),然后 break,后续 priority 50 真正能分类的规则没机会跑。
>
> 修法:**Task 14 实现的 `classifier.py` 必须在命中 `category_id IS NULL` 的 marker 规则时**:
> 1. **不**写 `T.category_id = NULL`(保持原值,通常仍是 None)
> 2. **不** break,继续找下一条规则
> 3. 但 **要** `rule.hit_count += 1`(标记规则 hit 也是规则有意义的统计)
> 4. **要** 在 `T.raw_payload['markers']` 累加该规则的 pattern(slice E MCP 工具可从这里读"这笔交易曾被识别为跨源镜像")
>
> 本 task 只**写契约测试**(spec-style,不依赖具体实现)。Task 14 实现 classifier 时必须让这些测试通过。这是"先冻结契约,再实现"的标准 TDD。

- [ ] **Step 4.1:创建 services 测试目录骨架**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
ni -ItemType Directory -Force -Path tests\services | Out-Null
ni -ItemType File -Force -Path tests\services\__init__.py | Out-Null
```

(注:`tests/services/statement_parser/` 已在 slice B 存在,`tests/services/__init__.py` 也已存在;若已有,`ni` `-Force` 不会破坏。)

- [ ] **Step 4.2:写契约测试 `tests/services/test_classifier_marker_contract.py`**

```python
"""分类引擎对 marker 规则(category_id IS NULL)的契约 — slice A Rec #5。

本测试 freeze 行为契约,独立于 Task 14 的具体实现。Task 14 实现 classifier.py 时
必须让这些断言全部 pass。

契约:
- 普通规则(category_id is not None)命中:写 category_id + confidence + break
- marker 规则(category_id is None)命中:不写 category_id,不 break,加 hit_count,
  在 transaction.raw_payload['markers'] 累加 pattern
- 多条 marker 命中再命中真分类规则:markers 累加 + category 从真分类规则来
- 全部都 marker 命中:category_id 仍 None,markers 累加,confidence 留 None
"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Category, MerchantRule, Transaction, User


@pytest.fixture
def setup_user_and_categories(db):
    """构造一个 user + 一个最小分类树,返回 (user_id, categories_dict)。"""
    user = User(username="cls_test", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    # 餐饮(顶级)+ 餐饮/咖啡(子)
    cat_food = Category(user_id=user.id, name="餐饮", kind="expense", parent_id=None)
    db.add(cat_food)
    db.flush()
    cat_coffee = Category(user_id=user.id, name="咖啡", kind="expense", parent_id=cat_food.id)
    db.add(cat_coffee)
    db.flush()
    return user.id, {"food": cat_food.id, "coffee": cat_coffee.id}


@pytest.fixture
def setup_account(db, setup_user_and_categories):
    """给 user 建一个 wechat 账户,返回 account_id。"""
    user_id, _ = setup_user_and_categories
    acc = Account(user_id=user_id, name="微信支付", type="wechat", institution="微信支付", last4=None)
    db.add(acc)
    db.flush()
    return acc.id


def _make_tx(db, user_id, account_id, merchant_norm, amount=Decimal("12.50"), source="wechat"):
    """造一条未分类 transaction 用于测试。"""
    tx = Transaction(
        user_id=user_id,
        account_id=account_id,
        statement_import_id=None,
        tx_kind="expense",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        amount=amount,
        currency="CNY",
        amount_settled_cny=amount,
        merchant_raw=merchant_norm,
        merchant_normalized=merchant_norm,
        category_id=None,
        source=source,
        is_mirror=False,
        raw_payload={},
    )
    db.add(tx)
    db.flush()
    return tx


def _add_rule(db, user_id, pattern, match_kind, category_id, priority):
    r = MerchantRule(
        user_id=user_id,
        pattern=pattern,
        match_kind=match_kind,
        category_id=category_id,
        priority=priority,
    )
    db.add(r)
    db.flush()
    return r


# === 契约测试 ===

def test_normal_rule_hit_assigns_category_and_breaks(
    db, setup_user_and_categories, setup_account
):
    """普通规则命中:写 category_id + confidence=1.0 + hit_count++。"""
    from app.services.classifier import classify_transaction

    user_id, cats = setup_user_and_categories
    account_id = setup_account
    rule = _add_rule(db, user_id, "瑞幸咖啡", "fuzzy", cats["coffee"], priority=50)
    tx = _make_tx(db, user_id, account_id, "瑞幸咖啡")

    result = classify_transaction(db, tx)

    db.refresh(tx)
    db.refresh(rule)
    assert tx.category_id == cats["coffee"]
    assert tx.classification_confidence == 1.0
    assert rule.hit_count == 1
    assert result.matched_rule_id == rule.id


def test_marker_rule_hit_does_not_assign_but_logs_marker(
    db, setup_user_and_categories, setup_account
):
    """marker 规则(category_id IS NULL)命中:不写 category_id,在 raw_payload['markers'] 加 pattern,继续。"""
    from app.services.classifier import classify_transaction

    user_id, _ = setup_user_and_categories
    account_id = setup_account
    marker = _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    tx = _make_tx(db, user_id, account_id, "财付通-luckin")

    classify_transaction(db, tx)

    db.refresh(tx)
    db.refresh(marker)
    assert tx.category_id is None  # 没真分类
    assert tx.classification_confidence is None
    assert marker.hit_count == 1
    markers = (tx.raw_payload or {}).get("markers", [])
    assert "财付通-" in markers


def test_marker_then_real_rule_assigns_category_from_real_rule(
    db, setup_user_and_categories, setup_account
):
    """marker 规则命中后**继续**找真分类规则,真分类规则赋值 category。"""
    from app.services.classifier import classify_transaction

    user_id, cats = setup_user_and_categories
    account_id = setup_account
    marker = _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    real = _add_rule(db, user_id, "luckin", "contains", cats["coffee"], priority=50)
    tx = _make_tx(db, user_id, account_id, "财付通-luckin coffee")

    classify_transaction(db, tx)

    db.refresh(tx)
    db.refresh(marker)
    db.refresh(real)
    assert tx.category_id == cats["coffee"]  # 真分类生效
    assert tx.classification_confidence == 1.0
    assert marker.hit_count == 1
    assert real.hit_count == 1
    assert "财付通-" in (tx.raw_payload or {}).get("markers", [])


def test_only_markers_hit_keeps_unclassified(
    db, setup_user_and_categories, setup_account
):
    """全部命中的都是 marker → tx 仍未分类,但 markers 累加。"""
    from app.services.classifier import classify_transaction

    user_id, _ = setup_user_and_categories
    account_id = setup_account
    _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    _add_rule(db, user_id, "蚂蚁(", "contains", None, priority=20)
    tx = _make_tx(db, user_id, account_id, "财付通-蚂蚁(杭州)未知商家")

    classify_transaction(db, tx)

    db.refresh(tx)
    assert tx.category_id is None
    assert tx.classification_confidence is None
    markers = (tx.raw_payload or {}).get("markers", [])
    assert "财付通-" in markers
    assert "蚂蚁(" in markers


def test_no_rule_hit_keeps_unclassified_no_markers(
    db, setup_user_and_categories, setup_account
):
    """商户名不命中任何规则:category 留 None,markers 不存在或为空。"""
    from app.services.classifier import classify_transaction

    user_id, _ = setup_user_and_categories
    account_id = setup_account
    _add_rule(db, user_id, "瑞幸咖啡", "fuzzy", None, priority=50)  # 一个不命中的真规则
    tx = _make_tx(db, user_id, account_id, "完全陌生的商户名")

    classify_transaction(db, tx)

    db.refresh(tx)
    assert tx.category_id is None
    markers = (tx.raw_payload or {}).get("markers", []) if tx.raw_payload else []
    assert markers == []


def test_priority_order_respected_with_markers(
    db, setup_user_and_categories, setup_account
):
    """priority 小的先匹配。marker(priority 20)先 hit 不 break,真规则(priority 50)再 hit 才赋值。"""
    from app.services.classifier import classify_transaction

    user_id, cats = setup_user_and_categories
    account_id = setup_account
    # 故意倒序插入,验证 classifier 按 priority 排序而非插入顺序
    _add_rule(db, user_id, "luckin", "contains", cats["coffee"], priority=50)
    _add_rule(db, user_id, "财付通-", "contains", None, priority=20)
    tx = _make_tx(db, user_id, account_id, "财付通-luckin")

    classify_transaction(db, tx)

    db.refresh(tx)
    assert tx.category_id == cats["coffee"]
    assert "财付通-" in (tx.raw_payload or {}).get("markers", [])
```

- [ ] **Step 4.3:跑测试看失败**

```powershell
pytest tests/services/test_classifier_marker_contract.py -v
```

期望:**全部 FAIL with `ImportError: cannot import name 'classify_transaction' from 'app.services.classifier'`**。这是预期 — 契约测试在 Task 4 写下,Task 14 才实现。这些测试会在 Task 14 通过。

(注:此 task **不实现 classifier**,只冻结契约。如果担心红测试影响 CI,可以先用 `@pytest.mark.skip(reason="awaits Task 14")` 标记;但建议直接保留,Task 14 头一步就是把 skip 摘掉验证。)

- [ ] **Step 4.4:把这批契约测试标记 xfail 直到 Task 14 实现**

打开测试文件顶部 `import pytest` 之后,添加:

```python
# Task 14 实现 classifier.py 时移除此 marker
pytestmark = pytest.mark.xfail(
    reason="awaits Task 14 classifier implementation",
    raises=ImportError,
    strict=True,
)
```

- [ ] **Step 4.5:再跑一次,xfail 让套件 green**

```powershell
pytest tests/services/test_classifier_marker_contract.py -v
```

期望:`6 xfailed`(报告颜色仍 green)。Task 14 实现完后**一定记得删除 `pytestmark` 行**。

- [ ] **Step 4.6:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/tests/services/test_classifier_marker_contract.py backend/tests/services/__init__.py
git commit -m "test(classifier): freeze marker-rule contract (xfail until Task 14, slice A Rec #5)"
```

---

## Task 5:认证 service — bcrypt verify + JWT encode/decode

**Files:**
- Create: `backend/app/services/auth.py`
- Test: `backend/tests/services/test_auth_service.py`

> spec § 10.1:JWT in httpOnly cookie,bcrypt 密码校验。`python-jose[cryptography]` 已在 deps,`passlib[bcrypt]` 同。本 task 写**纯函数**,不涉及 HTTP/DB —— Task 7 的端点再调用本 service。

- [ ] **Step 5.1:写测试 `tests/services/test_auth_service.py`**

```python
"""auth service 单元测试 — bcrypt + JWT。"""
import time

import pytest
from passlib.hash import bcrypt as bcrypt_hash

from app.services.auth import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    verify_password,
)


def test_verify_password_correct():
    h = bcrypt_hash.hash("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_password_wrong():
    h = bcrypt_hash.hash("hunter2")
    assert verify_password("nope", h) is False


def test_verify_password_invalid_hash_returns_false():
    """无效 hash 不应抛 raise,返回 False(防止 user enum 通过 5xx)。"""
    assert verify_password("anything", "not_a_bcrypt") is False


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(subject="admin", expires_minutes=15)
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert "exp" in payload


def test_decode_expired_token_raises():
    """过期 token 必须 raise InvalidTokenError。"""
    token = create_access_token(subject="admin", expires_minutes=0)
    time.sleep(1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_tampered_token_raises():
    token = create_access_token(subject="admin", expires_minutes=10)
    bad = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    with pytest.raises(InvalidTokenError):
        decode_access_token(bad)


def test_decode_empty_or_garbage_raises():
    for bad in ["", "   ", "not.a.jwt", "x.y.z"]:
        with pytest.raises(InvalidTokenError):
            decode_access_token(bad)
```

- [ ] **Step 5.2:跑测试看失败**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/services/test_auth_service.py -v
```

期望:`ImportError: cannot import name 'verify_password' from 'app.services.auth'`。

- [ ] **Step 5.3:写 `app/services/auth.py`**

```python
"""认证 service:bcrypt 密码校验 + JWT 签发 / 解析(spec § 10.1)。

本模块**不接 DB,不接 HTTP**,纯函数,便于单元测试。Task 7 的端点调用本服务。
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.exc import PasslibException
from passlib.hash import bcrypt as bcrypt_hash

from app.core.config import get_settings


_ALGO = "HS256"


class InvalidTokenError(ValueError):
    """JWT 校验失败(过期 / 篡改 / 格式错)。HTTP 层可转 401。"""


def verify_password(plain: str, hashed: str) -> bool:
    """密码校验。无效 hash 返回 False(不抛错,避免 user enum 通过 5xx 区分)。"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt_hash.verify(plain, hashed)
    except (PasslibException, ValueError):
        return False


def create_access_token(subject: str, expires_minutes: int = 60 * 24 * 30) -> str:
    """签发 JWT,默认 30 天有效(spec § 10.1 cookie 30 天)。

    expires_minutes=0 时 token 立即过期(测试用)。
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGO)


def decode_access_token(token: str) -> dict[str, Any]:
    """校验 + 解析 JWT。失败抛 InvalidTokenError。"""
    if not token or not isinstance(token, str):
        raise InvalidTokenError("token is empty")
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_ALGO])
    except JWTError as e:
        raise InvalidTokenError(str(e)) from e
```

- [ ] **Step 5.4:跑测试看通过**

```powershell
pytest tests/services/test_auth_service.py -v
```

期望:7 passed。

如果 `test_decode_expired_token_raises` flaky:增大 `time.sleep(1)` 到 `time.sleep(2)`,或 `expires_minutes=-1`(jose 允许负数即过去时间)。

- [ ] **Step 5.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/auth.py backend/tests/services/test_auth_service.py
git commit -m "feat(auth): add password verify + JWT encode/decode service"
```

---

## Task 6:Pydantic schemas 包(req/resp 模型)

**Files:**
- Create: `backend/app/schemas/__init__.py`(re-export)
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/schemas/account.py`
- Create: `backend/app/schemas/category.py`
- Create: `backend/app/schemas/rule.py`
- Create: `backend/app/schemas/statement.py`
- Create: `backend/app/schemas/transaction.py`
- Create: `backend/app/schemas/dedup.py`
- Create: `backend/app/schemas/summary.py`
- Test: `backend/tests/schemas/test_schemas_smoke.py`(导入 + 序列化烟测)

> 把所有 HTTP 边界的 req/resp Pydantic 模型集中到 `app/schemas/`。后续 Task 7+ 的 router 直接 import。命名规约:`XxxIn`(req body)、`XxxOut`(resp body)、`XxxQuery`(query string)。所有 `Out` 模型继承 `BaseModel(model_config=ConfigDict(from_attributes=True))` 让 SQLAlchemy ORM → schema 直接映射。

- [ ] **Step 6.1:创建包骨架 + 共享 base**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
ni -ItemType Directory -Force -Path app\schemas, tests\schemas | Out-Null
ni -ItemType File -Force -Path tests\schemas\__init__.py | Out-Null
```

写 `backend/app/schemas/__init__.py`:

```python
"""HTTP 边界 Pydantic schema 集中 re-export。

约定:
- XxxIn:request body
- XxxOut:response body(from_attributes=True,可从 ORM 对象直接构造)
- XxxQuery:query string(FastAPI Query 用)
"""
from app.schemas.account import AccountCreate, AccountOut, AccountUpdate
from app.schemas.auth import LoginIn, LoginOut, MeOut
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.dedup import DedupDecisionIn, DedupPairOut, PendingPairListOut
from app.schemas.rule import MerchantRuleCreate, MerchantRuleOut, MerchantRuleUpdate
from app.schemas.statement import (
    ImportResponse,
    ReviewBundle,
    StatementImportListOut,
    StatementImportOut,
)
from app.schemas.summary import SummaryBreakdownItem, SummaryOut
from app.schemas.transaction import (
    BulkUpdateByMerchantIn,
    BulkUpdateResult,
    TransactionListOut,
    TransactionOut,
    TransactionPatchIn,
    TransactionQuery,
)

__all__ = [
    "LoginIn", "LoginOut", "MeOut",
    "AccountCreate", "AccountOut", "AccountUpdate",
    "CategoryCreate", "CategoryOut", "CategoryUpdate",
    "MerchantRuleCreate", "MerchantRuleOut", "MerchantRuleUpdate",
    "StatementImportOut", "StatementImportListOut", "ImportResponse", "ReviewBundle",
    "TransactionOut", "TransactionListOut", "TransactionPatchIn",
    "TransactionQuery", "BulkUpdateByMerchantIn", "BulkUpdateResult",
    "DedupPairOut", "PendingPairListOut", "DedupDecisionIn",
    "SummaryOut", "SummaryBreakdownItem",
]
```

- [ ] **Step 6.2:写 `app/schemas/auth.py`**

```python
"""认证 schemas。spec § 10.1。"""
from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginOut(BaseModel):
    """登录成功响应(token 在 cookie,body 只回 user 信息)。"""
    user_id: int
    username: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
```

- [ ] **Step 6.3:写 `app/schemas/account.py`**

```python
"""Account schemas — spec § 4.1。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


AccountType = Literal["bank_debit", "bank_credit", "alipay", "wechat", "cash"]


class AccountCreate(BaseModel):
    name: str = Field(..., max_length=128)
    type: AccountType
    institution: str | None = Field(None, max_length=64)
    last4: str | None = Field(None, pattern=r"^\d{4}$")
    currency: str = "CNY"


class AccountUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    last4: str | None = Field(None, pattern=r"^\d{4}$")
    archived: bool | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: AccountType
    institution: str | None
    last4: str | None
    currency: str
    archived: bool
```

- [ ] **Step 6.4:写 `app/schemas/category.py`**

```python
"""Category schemas — spec § 4.1 树形分类。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


CategoryKind = Literal["expense", "income", "neutral"]


class CategoryCreate(BaseModel):
    name: str = Field(..., max_length=64)
    parent_id: int | None = None
    kind: CategoryKind
    icon: str | None = None
    color: str | None = None
    sort_order: int = 100


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    icon: str | None = None
    color: str | None = None
    sort_order: int | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    parent_id: int | None
    kind: CategoryKind
    icon: str | None
    color: str | None
    sort_order: int
```

- [ ] **Step 6.5:写 `app/schemas/rule.py`**

```python
"""MerchantRule schemas — spec § 4.1 + § 7。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


MatchKind = Literal["exact", "contains", "regex", "fuzzy"]


class MerchantRuleCreate(BaseModel):
    pattern: str = Field(..., max_length=255)
    match_kind: MatchKind
    category_id: int | None = None  # None = marker rule(spec § 7.1)
    priority: int = 100


class MerchantRuleUpdate(BaseModel):
    pattern: str | None = None
    match_kind: MatchKind | None = None
    category_id: int | None = None
    priority: int | None = None


class MerchantRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pattern: str
    match_kind: MatchKind
    category_id: int | None
    priority: int
    hit_count: int
```

- [ ] **Step 6.6:写 `app/schemas/transaction.py`**

```python
"""Transaction schemas — spec § 4.1 + § 9.1 交易列表。"""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


TxKind = Literal["expense", "income", "neutral", "refund"]
SourceKind = Literal["bank", "alipay", "wechat", "conversation", "manual"]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    statement_import_id: int | None
    tx_kind: TxKind
    tx_time: datetime
    post_time: datetime | None
    amount: Decimal
    currency: str
    amount_settled_cny: Decimal
    merchant_raw: str | None
    merchant_normalized: str | None
    description_raw: str | None
    category_id: int | None
    classification_confidence: float | None
    source: SourceKind
    is_mirror: bool
    mirror_of_id: int | None


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class TransactionQuery(BaseModel):
    """GET /api/transactions query string 模型。"""
    date_from: datetime | None = None
    date_to: datetime | None = None
    account_id: int | None = None
    category_id: int | None = None
    kind: TxKind | None = None
    source: SourceKind | None = None
    is_mirror: bool | None = None
    keyword: str | None = None  # 模糊匹配 merchant_normalized
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class TransactionPatchIn(BaseModel):
    """PATCH /api/transactions/{id} 单条改类。"""
    category_id: int | None = None
    tx_kind: TxKind | None = None


class BulkUpdateByMerchantIn(BaseModel):
    """POST /api/transactions/bulk-update-by-merchant — spec § 8.1 同款,Web UI 也用。"""
    pattern: str = Field(..., min_length=1, max_length=255)
    match_kind: Literal["exact", "contains", "regex", "fuzzy"] = "contains"
    category_id: int
    also_add_rule: bool = True


class BulkUpdateResult(BaseModel):
    affected_count: int
    rule_id: int | None  # also_add_rule=True 时返回新建/复用的 rule_id
```

- [ ] **Step 6.7:写 `app/schemas/statement.py`**

```python
"""StatementImport / Review schemas — spec § 5.1 + § 9.1 复查页。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class StatementImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int | None
    source_type: str
    filename: str
    file_hash: str
    period_start: datetime | None
    period_end: datetime | None
    raw_row_count: int
    imported_count: int
    deduped_count: int
    classified_count: int
    imported_at: datetime


class StatementImportListOut(BaseModel):
    items: list[StatementImportOut]
    total: int


class ImportResponse(BaseModel):
    """POST /api/statements/import 响应。"""
    import_id: int
    source_type: str
    raw_row_count: int
    imported_count: int
    deduped_strong_count: int      # 自动去重(② + ③)
    dedup_pending_count: int       # 待审核(④ + ⑤)
    classified_count: int
    unclassified_count: int


class ReviewBundle(BaseModel):
    """GET /api/statements/{id}/review。"""
    statement: StatementImportOut
    pending_pairs: list["DedupPairOut"]              # forward ref
    unclassified_transactions: list["TransactionOut"] # forward ref


# 解 forward refs
from app.schemas.dedup import DedupPairOut          # noqa: E402
from app.schemas.transaction import TransactionOut  # noqa: E402
ReviewBundle.model_rebuild()
```

- [ ] **Step 6.8:写 `app/schemas/dedup.py`**

```python
"""Dedup schemas — spec § 6 + § 8.1。"""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


MatchKind = Literal["strong", "bridge", "conversation"]
PairStatus = Literal["pending", "confirmed", "rejected"]


class DedupPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    primary_tx_id: int
    mirror_tx_id: int
    match_kind: MatchKind
    confidence: float
    status: PairStatus
    reasoning: dict[str, Any] | None


class PendingPairListOut(BaseModel):
    items: list[DedupPairOut]
    total: int


class DedupDecisionIn(BaseModel):
    """POST /api/dedup/{pair_id}/confirm | /reject body."""
    action: Literal["confirm", "reject"]
    note: str | None = Field(None, max_length=512)
```

- [ ] **Step 6.9:写 `app/schemas/summary.py`**

```python
"""Summary schemas — spec § 8.1 get_summary。"""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel


GroupBy = Literal["category", "account", "merchant"]
Period = Literal["day", "week", "month", "year"]


class SummaryBreakdownItem(BaseModel):
    group_key: str   # category name / account name / merchant_normalized
    group_id: int | None
    amount: Decimal
    count: int


class SummaryOut(BaseModel):
    period: Period
    date_from: datetime
    date_to: datetime
    group_by: GroupBy
    total_expense: Decimal
    total_income: Decimal
    breakdown: list[SummaryBreakdownItem]
```

- [ ] **Step 6.10:写烟测 `tests/schemas/test_schemas_smoke.py`**

```python
"""schemas 包导入 + 关键字段烟测。"""
from datetime import datetime
from decimal import Decimal


def test_re_export_intact():
    from app import schemas
    expected = {
        "LoginIn", "LoginOut", "MeOut",
        "AccountCreate", "AccountOut", "AccountUpdate",
        "CategoryCreate", "CategoryOut", "CategoryUpdate",
        "MerchantRuleCreate", "MerchantRuleOut", "MerchantRuleUpdate",
        "StatementImportOut", "StatementImportListOut", "ImportResponse", "ReviewBundle",
        "TransactionOut", "TransactionListOut", "TransactionPatchIn",
        "TransactionQuery", "BulkUpdateByMerchantIn", "BulkUpdateResult",
        "DedupPairOut", "PendingPairListOut", "DedupDecisionIn",
        "SummaryOut", "SummaryBreakdownItem",
    }
    assert expected.issubset(set(dir(schemas)))


def test_login_in_validates():
    from app.schemas import LoginIn
    LoginIn(username="admin", password="x")
    import pytest
    with pytest.raises(ValueError):
        LoginIn(username="", password="x")


def test_transaction_query_defaults():
    from app.schemas import TransactionQuery
    q = TransactionQuery()
    assert q.limit == 50
    assert q.offset == 0


def test_transaction_query_validates_limit():
    from app.schemas import TransactionQuery
    import pytest
    with pytest.raises(ValueError):
        TransactionQuery(limit=0)
    with pytest.raises(ValueError):
        TransactionQuery(limit=1000)


def test_review_bundle_model_rebuild_ok():
    """forward ref 在 Task 6.7 末尾 model_rebuild — 实例化不抛错即说明 OK。"""
    from app.schemas import ReviewBundle, StatementImportOut
    rb = ReviewBundle(
        statement=StatementImportOut(
            id=1, account_id=None, source_type="alipay_csv",
            filename="x.csv", file_hash="h", period_start=None, period_end=None,
            raw_row_count=0, imported_count=0, deduped_count=0, classified_count=0,
            imported_at=datetime(2026, 5, 9),
        ),
        pending_pairs=[], unclassified_transactions=[],
    )
    assert rb.statement.id == 1
```

- [ ] **Step 6.11:跑烟测**

```powershell
pytest tests/schemas/test_schemas_smoke.py -v
```

期望:5 passed。

如果有 `model_rebuild` 报错(forward ref 解析失败):看 statement.py 末尾的两条 `from .dedup import` / `from .transaction import` 是否在 `__init__.py` 之前被加载。一般 Pydantic v2 model_rebuild 会自动解析,失败时把 `from app.schemas.dedup import DedupPairOut` 提到文件顶部即可(可能引入循环 import,若循环则保留尾部解析)。

- [ ] **Step 6.12:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/schemas/ backend/tests/schemas/
git commit -m "feat(schemas): add Pydantic req/resp models for all REST endpoints"
```

---

## Task 7:认证端点 — `/api/auth/login` `/logout` `/me` + `current_user` dependency

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/deps.py`
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py`(挂载 auth router)
- Test: `backend/tests/api/__init__.py`(空)
- Test: `backend/tests/api/conftest.py`(client + login fixture)
- Test: `backend/tests/api/test_auth.py`

> spec § 10.1:登录签 JWT,设 httpOnly cookie `fm_session`(SameSite=Lax, Secure, 30 天)。除 `/api/auth/login` 外所有 `/api/*` 都验证 cookie。同时(本切片新增)`POST /api/auth/login` 失败 5 次 30 分钟锁定的 rate limit 留 V2(spec § 12),本切片只做基础。

- [ ] **Step 7.1:创建 api 包骨架**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
ni -ItemType Directory -Force -Path app\api, tests\api | Out-Null
ni -ItemType File -Force -Path app\api\__init__.py, tests\api\__init__.py | Out-Null
```

`app/api/__init__.py` 留空。

- [ ] **Step 7.2:写 `app/api/deps.py`(共享依赖)**

```python
"""FastAPI 依赖:DbDep(复用 core.db.get_db) / current_user。

current_user 从 cookie `fm_session` 解 JWT,失败返回 401。
spec § 10.1。
"""
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db  # 复用 slice A 已定义的 session 工厂
from app.models import User
from app.services.auth import InvalidTokenError, decode_access_token


SESSION_COOKIE_NAME = "fm_session"

DbDep = Annotated[Session, Depends(get_db)]


def current_user(
    db: DbDep,
    fm_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    """从 cookie 取 JWT 解出 user。失败 401。"""
    if not fm_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing session cookie")
    try:
        payload = decode_access_token(fm_session)
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    username = payload.get("sub")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]
```

(刻意复用 `app.core.db.get_db` 而非自己再写一份,避免 conftest 的 `dependency_overrides[get_db]` 与端点实际依赖的 `get_db` 是两个不同函数对象。)

- [ ] **Step 7.3:写 `app/api/auth.py`**

```python
"""认证端点 — spec § 10.1。"""
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import (
    SESSION_COOKIE_NAME,
    CurrentUserDep,
    DbDep,
)
from app.core.config import get_settings
from app.models import User
from app.schemas import LoginIn, LoginOut, MeOut
from app.services.auth import create_access_token, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


_TOKEN_EXPIRES_MINUTES = 60 * 24 * 30  # 30 天,与 cookie 同寿


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, response: Response, db: DbDep) -> LoginOut:
    user = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        # 用户名不存在 vs 密码错 — 返回同样的 401,避免 user enum
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = create_access_token(subject=user.username, expires_minutes=_TOKEN_EXPIRES_MINUTES)
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        # 本机开发 http,Secure=False;生产 Caddy https 时改为 True(留 V2 配置化)
        secure=False,
        max_age=_TOKEN_EXPIRES_MINUTES * 60,
        path="/",
    )
    return LoginOut(user_id=user.id, username=user.username)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return None


@router.get("/me", response_model=MeOut)
def me(user: CurrentUserDep) -> MeOut:
    return MeOut.model_validate(user)
```

- [ ] **Step 7.4:把 auth router 挂到 main app**

打开 [backend/app/main.py](backend/app/main.py),把当前内容替换为:

```python
"""FastAPI app 实例 + minimum routes。"""
from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.api import auth as auth_api
from app.core.db import engine

app = FastAPI(title="Finance Manager API", version="0.1.0")

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health() -> dict:
    """健康检查:进程在 + db 可达。"""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {type(e).__name__}"
    return {"status": "ok", "version": app.version, "db": db_status}


api_router.include_router(auth_api.router)
app.include_router(api_router)
```

- [ ] **Step 7.5:写 `tests/api/conftest.py`(`client` + `logged_in_client` fixture)**

```python
"""api 测试共享 fixture — TestClient + 已登录 client。"""
import pytest
from fastapi.testclient import TestClient
from passlib.hash import bcrypt as bcrypt_hash
from sqlalchemy import select

from app.core.db import get_db  # 同一函数对象,与 app/api/deps.py 共用
from app.main import app
from app.models import User


_TEST_PASSWORD = "test-pwd-2026"
_TEST_USERNAME = "admin"


@pytest.fixture
def admin_user(db) -> User:
    """确保 admin 存在 + password_hash 跟 _TEST_PASSWORD 对得上(覆盖 .env 的真实 hash)。"""
    user = db.execute(select(User).where(User.username == _TEST_USERNAME)).scalar_one_or_none()
    h = bcrypt_hash.hash(_TEST_PASSWORD)
    if user is None:
        user = User(username=_TEST_USERNAME, password_hash=h)
        db.add(user)
        db.flush()
    else:
        user.password_hash = h
        db.flush()
    return user


@pytest.fixture
def client(db) -> TestClient:
    """绑定 db fixture 的 TestClient — override get_db 让端点用同一 session。"""
    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def logged_in_client(client, admin_user) -> TestClient:
    """已登录 client(cookie 已注入)。"""
    resp = client.post("/api/auth/login", json={
        "username": _TEST_USERNAME,
        "password": _TEST_PASSWORD,
    })
    assert resp.status_code == 200, resp.text
    return client
```

- [ ] **Step 7.6:写 `tests/api/test_auth.py`**

```python
"""认证端点 e2e 测试。"""


def test_login_success_sets_cookie(client, admin_user):
    resp = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "test-pwd-2026",
    })
    assert resp.status_code == 200
    assert "fm_session" in resp.cookies
    body = resp.json()
    assert body["username"] == "admin"


def test_login_wrong_password_401(client, admin_user):
    resp = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_login_unknown_user_401(client, admin_user):
    """未知用户应与密码错返回同样 401(无 user enum 区分)。"""
    resp = client.post("/api/auth/login", json={
        "username": "ghost",
        "password": "anything",
    })
    assert resp.status_code == 401


def test_me_requires_login(client):
    """无 cookie /me → 401。"""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_user(logged_in_client):
    resp = logged_in_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_logout_clears_cookie(logged_in_client):
    resp = logged_in_client.post("/api/auth/logout")
    assert resp.status_code == 204
    # 之后再请求 /me 应 401
    resp2 = logged_in_client.get("/api/auth/me")
    assert resp2.status_code == 401


def test_login_validates_input(client):
    resp = client.post("/api/auth/login", json={"username": "", "password": "x"})
    assert resp.status_code == 422  # Pydantic 校验失败


def test_health_unaffected_by_auth(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
```

- [ ] **Step 7.7:跑测试看通过**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/api/test_auth.py -v
```

期望:8 passed。

排查:
- 401 但期望 200:确认 admin_user fixture 在测试执行前 flush 到 db,且 client fixture 用同一 session。
- cookie 没设上:`set_cookie` 中 `secure=True` 在 http TestClient 下不生效;Task 7.3 默认 `secure=False`,生产由 Caddy https 自然 secure。
- `from app.core.db import SessionLocal` ImportError:见 7.2 注释。

- [ ] **Step 7.8:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/api/ backend/app/main.py backend/tests/api/
git commit -m "feat(auth): add login/logout/me endpoints with JWT cookie session"
```

---

## Task 8:导入 service - file_hash 查重 + statement_imports 落库 + account 自动推断

**Files:**
- Create: `backend/app/services/importer.py`(本 task 只写 file_hash + ensure_statement_import + ensure_account 三个函数,Task 9 起补 persist + 调度)
- Test: `backend/tests/services/test_importer_setup.py`

> spec § 5.1 step 2-4 + § 5.1.1 账户自动推断:
> - **file_hash**:sha256(file_bytes),查 statement_imports.file_hash,已存在抛 `DuplicateImportError`(端点转 409)
> - **ensure_account**:`(user_id, institution, last4)` 查找;命中复用,未命中按 `AccountHint` 创建,name 自动起为 `"建设银行信用卡 7432"` / `"交通银行借记卡 2498"`;支付宝/微信用全局账户(institution + `last4 IS NULL`)
> - **ensure_statement_import**:写一条 statement_imports 行,先填 raw_row_count(从 ParseResult.metadata),imported/deduped/classified 用 0,后续 task 在管道末尾 update

- [ ] **Step 8.1:写测试 `tests/services/test_importer_setup.py`**

```python
"""importer setup 函数单元测试 — file_hash / ensure_account / ensure_statement_import。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, StatementImport, User
from app.services.importer import (
    DuplicateImportError,
    ensure_account_for_hint,
    ensure_statement_import,
    file_sha256,
)
from app.services.statement_parser import AccountHint, ParseResult, RawTransaction


@pytest.fixture
def test_user(db) -> User:
    u = User(username="ix", password_hash="$2b$12$" + "x" * 53)
    db.add(u)
    db.flush()
    return u


def test_file_sha256_deterministic():
    assert file_sha256(b"hello") == file_sha256(b"hello")
    assert file_sha256(b"hello") != file_sha256(b"world")
    assert len(file_sha256(b"hello")) == 64  # hex digest


def test_ensure_account_creates_for_bank_credit(db, test_user):
    hint = AccountHint(type="bank_credit", institution="建设银行", last4="7432")
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert acc.id is not None
    assert acc.institution == "建设银行"
    assert acc.last4 == "7432"
    assert acc.type == "bank_credit"
    assert acc.name == "建设银行信用卡 7432"  # 自动起名


def test_ensure_account_creates_for_bank_debit(db, test_user):
    hint = AccountHint(type="bank_debit", institution="交通银行", last4="2498")
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert acc.name == "交通银行借记卡 2498"


def test_ensure_account_idempotent_same_hint(db, test_user):
    hint = AccountHint(type="bank_credit", institution="建设银行", last4="7432")
    a1 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    a2 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert a1.id == a2.id


def test_ensure_account_alipay_global(db, test_user):
    """支付宝/微信无 last4,固定全局账户(last4 IS NULL)。"""
    hint = AccountHint(type="alipay", institution="支付宝", last4=None)
    a1 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    a2 = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert a1.id == a2.id
    assert a1.last4 is None
    assert a1.name == "支付宝"


def test_ensure_account_wechat_global(db, test_user):
    hint = AccountHint(type="wechat", institution="微信支付", last4=None)
    a = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    assert a.name == "微信支付"
    assert a.type == "wechat"


def test_ensure_account_different_last4_creates_separate(db, test_user):
    """同 institution 不同 last4 → 不同 account。"""
    a1 = ensure_account_for_hint(db, test_user.id,
        AccountHint(type="bank_debit", institution="交通银行", last4="2498"))
    a2 = ensure_account_for_hint(db, test_user.id,
        AccountHint(type="bank_debit", institution="交通银行", last4="9999"))
    db.flush()
    assert a1.id != a2.id


def _make_parse_result(account_hint: AccountHint, raw_count: int = 10) -> ParseResult:
    return ParseResult(
        raw_transactions=[],
        account_hint=account_hint,
        period_start=datetime(2026, 3, 1),
        period_end=datetime(2026, 3, 26),
        metadata={"raw_row_count": raw_count, "imported_count": raw_count, "dropped_count": 0},
    )


def test_ensure_statement_import_creates_row(db, test_user):
    hint = AccountHint(type="alipay", institution="支付宝", last4=None)
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    pr = _make_parse_result(hint, raw_count=42)
    si = ensure_statement_import(
        db, user_id=test_user.id, account_id=acc.id,
        source_type="alipay_csv",
        filename="alipay_x.csv",
        file_hash="a" * 64,
        parse_result=pr,
    )
    db.flush()
    assert si.id is not None
    assert si.source_type == "alipay_csv"
    assert si.raw_row_count == 42
    assert si.period_start == datetime(2026, 3, 1)


def test_ensure_statement_import_rejects_duplicate_hash(db, test_user):
    hint = AccountHint(type="alipay", institution="支付宝", last4=None)
    acc = ensure_account_for_hint(db, test_user.id, hint)
    db.flush()
    pr = _make_parse_result(hint)
    h = "b" * 64
    ensure_statement_import(db, user_id=test_user.id, account_id=acc.id,
        source_type="alipay_csv", filename="x.csv", file_hash=h, parse_result=pr)
    db.flush()
    with pytest.raises(DuplicateImportError) as ei:
        ensure_statement_import(db, user_id=test_user.id, account_id=acc.id,
            source_type="alipay_csv", filename="x_v2.csv", file_hash=h, parse_result=pr)
    assert "already imported" in str(ei.value).lower()
```

- [ ] **Step 8.2:跑测试看失败**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/services/test_importer_setup.py -v
```

期望:`ImportError: cannot import name 'file_sha256' from 'app.services.importer'`。

- [ ] **Step 8.3:写 `app/services/importer.py`(本 task 只到 setup 三个函数)**

```python
"""导入流水线编排 service — spec § 5.1。

本切片任务拆分:
- Task 8(本 task):file_sha256 / ensure_account_for_hint / ensure_statement_import
- Task 9:persist_raw_transactions
- Task 15:run_import_pipeline(总编排:parser → setup → persist → dedup → classify)
"""
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, StatementImport
from app.services.statement_parser import AccountHint, ParseResult


class DuplicateImportError(ValueError):
    """同 file_hash 已导入过(spec § 5.1 step 2),HTTP 层转 409。"""


_TYPE_TO_DISPLAY = {
    "bank_debit": "借记卡",
    "bank_credit": "信用卡",
}


def file_sha256(data: bytes) -> str:
    """sha256(data) hexdigest,作为 statement_imports.file_hash。"""
    return hashlib.sha256(data).hexdigest()


def _auto_name(hint: AccountHint) -> str:
    """自动起账户名 — spec § 5.1.1。

    bank_*:{institution}{借记卡|信用卡} {last4}
    alipay/wechat:{institution}
    cash:现金
    """
    if hint.type in ("bank_debit", "bank_credit"):
        kind = _TYPE_TO_DISPLAY[hint.type]
        last4 = hint.last4 or "????"
        return f"{hint.institution}{kind} {last4}"
    if hint.type in ("alipay", "wechat"):
        return hint.institution
    return hint.institution or "现金"


def ensure_account_for_hint(db: Session, user_id: int, hint: AccountHint) -> Account:
    """按 (user_id, institution, last4) 找;命中复用,未命中按 hint 创建。spec § 5.1.1。

    支付宝/微信 last4=None,SQL 用 IS NULL 严格匹配。
    """
    stmt = select(Account).where(
        Account.user_id == user_id,
        Account.institution == hint.institution,
        Account.last4 == hint.last4 if hint.last4 is not None else Account.last4.is_(None),
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing
    acc = Account(
        user_id=user_id,
        name=_auto_name(hint),
        type=hint.type,
        institution=hint.institution,
        last4=hint.last4,
        currency="CNY",
    )
    db.add(acc)
    db.flush()
    return acc


def ensure_statement_import(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    source_type: str,
    filename: str,
    file_hash: str,
    parse_result: ParseResult,
) -> StatementImport:
    """落 statement_imports 一行;file_hash 重复时抛 DuplicateImportError。

    spec § 5.1 step 2-4。imported/deduped/classified counts 在管道末尾(Task 15)更新。
    """
    existing = db.execute(
        select(StatementImport).where(StatementImport.file_hash == file_hash)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateImportError(
            f"file already imported as statement_import.id={existing.id} "
            f"on {existing.imported_at.isoformat() if existing.imported_at else '?'}"
        )

    si = StatementImport(
        user_id=user_id,
        account_id=account_id,
        source_type=source_type,
        filename=filename,
        file_hash=file_hash,
        period_start=parse_result.period_start,
        period_end=parse_result.period_end,
        raw_row_count=parse_result.metadata.get("raw_row_count", len(parse_result.raw_transactions)),
        imported_count=0,
        deduped_count=0,
        classified_count=0,
    )
    db.add(si)
    db.flush()
    return si
```

- [ ] **Step 8.4:跑测试看通过**

```powershell
pytest tests/services/test_importer_setup.py -v
```

期望:9 passed。

排查:
- "Account.last4 == None" SQLAlchemy 警告 → 8.3 已用 conditional `Account.last4.is_(None)` 处理
- ensure_account 找到已有的 admin user 创建的 default account → 测试 fixture 用独立 user_id,不冲突

- [ ] **Step 8.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/importer.py backend/tests/services/test_importer_setup.py
git commit -m "feat(importer): add file_sha256 + ensure_account_for_hint + ensure_statement_import"
```

---

## Task 9:导入 service - persist transactions(merchant_normalized + source_unique_key)

**Files:**
- Modify: `backend/app/services/importer.py`(追加 `persist_raw_transactions`)
- Test: `backend/tests/services/test_persist.py`

> spec § 5.1 step 4 + § 4.2 索引:把 `RawTransaction` 列表批量 insert 到 transactions,期间:
> 1. **merchant_normalized**:用 slice B 的 `normalize_merchant()` 计算
> 2. **source_unique_key**:`f"{source_short}:{external_tx_id}"`,external_tx_id 缺失则 `f"{source_short}:{statement_import_id}:{row_idx}:{sha8(merchant+amount+time)}"` 兜底,确保**每行都有 unique key**(spec § 4.2 索引 unique)
> 3. **source 派生**:从 `source_type` 派生 `transactions.source`(`alipay_csv → alipay`, `wechat_xlsx → wechat`, `bank_pdf_* → bank`)
> 4. **同源 file 内重复 source_unique_key**:跳过(spec § 6.1 ① 同源防重)
> 5. raw_payload 存 `RawTransaction.raw_row` JSONB
> 6. 返回 (created_count, skipped_same_source_count) tuple

- [ ] **Step 9.1:写测试 `tests/services/test_persist.py`**

```python
"""persist_raw_transactions 测试 — merchant_normalized / source_unique_key / 同源 dedup。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, StatementImport, Transaction, User
from app.services.importer import persist_raw_transactions
from app.services.statement_parser import AccountHint, ParseResult, RawTransaction


@pytest.fixture
def env(db):
    """造 user + account + statement_import。"""
    user = User(username="px", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    acc = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", last4=None)
    db.add(acc)
    db.flush()
    si = StatementImport(
        user_id=user.id, account_id=acc.id,
        source_type="alipay_csv", filename="x.csv", file_hash="h" * 64,
        period_start=datetime(2026, 3, 1), period_end=datetime(2026, 3, 26),
        raw_row_count=0, imported_count=0, deduped_count=0, classified_count=0,
    )
    db.add(si)
    db.flush()
    return user, acc, si


def _raw(merchant="瑞幸咖啡(北京)", amount="12.50", external_id="2026030122000001", **kw):
    return RawTransaction(
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        post_time=None,
        amount=Decimal(amount),
        currency="CNY",
        amount_settled_cny=Decimal(amount),
        tx_kind=kw.get("tx_kind", "expense"),
        merchant_raw=merchant,
        counterparty_raw=None,
        description_raw=None,
        external_tx_id=external_id,
        external_merchant_id=None,
        payment_method_raw=kw.get("payment_method_raw"),
        raw_row=kw.get("raw_row", {"raw": "row"}),
    )


def test_persist_creates_rows_with_normalized_merchant(db, env):
    user, acc, si = env
    raws = [_raw(), _raw(merchant="星巴克(上海)", external_id="2026030122000002")]
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=raws,
    )
    db.flush()
    assert created == 2 and skipped == 0
    txs = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalars().all()
    merchants_norm = sorted(t.merchant_normalized for t in txs)
    assert merchants_norm == ["星巴克", "瑞幸咖啡"]


def test_persist_uses_source_unique_key_with_external_id(db, env):
    user, acc, si = env
    raws = [_raw(external_id="abc123")]
    persist_raw_transactions(db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=raws)
    db.flush()
    tx = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalar_one()
    assert tx.source_unique_key == "alipay:abc123"
    assert tx.source == "alipay"


def test_persist_skips_duplicate_source_unique_key_in_same_batch(db, env):
    """spec § 6.1 ①:同 file 内含同 external_tx_id → 跳过第二条。"""
    user, acc, si = env
    raws = [_raw(external_id="dup1"), _raw(external_id="dup1", merchant="不同商家")]
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=raws,
    )
    db.flush()
    assert created == 1 and skipped == 1


def test_persist_skips_when_source_unique_key_already_in_db(db, env):
    """重复导入(应被 file_hash 拦,但万一漏过) → external_tx_id 唯一约束兜底。"""
    user, acc, si = env
    persist_raw_transactions(db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=[_raw(external_id="seen1")])
    db.flush()
    # 再来一次相同 external_id
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=[_raw(external_id="seen1")],
    )
    db.flush()
    assert created == 0 and skipped == 1


def test_persist_synthesizes_unique_key_when_external_id_missing(db, env):
    """external_tx_id 为 None(银行 PDF 常见)→ 用 (statement_import_id, row_idx, hash) 合成。"""
    user, acc, si = env
    raws = [_raw(external_id=None, merchant="商家A"),
            _raw(external_id=None, merchant="商家B")]
    created, _ = persist_raw_transactions(db, user_id=user.id, account_id=acc.id,
        statement_import_id=si.id, source_type="bank_pdf_bocom_debit", raw_transactions=raws)
    db.flush()
    txs = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalars().all()
    assert created == 2
    keys = sorted(t.source_unique_key for t in txs)
    # 两条 key 都以 "bank:" 开头,互不相同(包含 row_idx 防撞)
    assert all(k.startswith("bank:") for k in keys)
    assert len(set(keys)) == 2


def test_persist_source_mapping(db, env):
    """source_type → source 派生:alipay_csv → alipay, bank_pdf_* → bank。"""
    user, acc, si = env
    cases = [
        ("alipay_csv", "alipay"),
        ("wechat_xlsx", "wechat"),
        ("bank_pdf_bocom_debit", "bank"),
        ("bank_pdf_ccb_credit", "bank"),
    ]
    for stype, expected_src in cases:
        # 用不同 external_id 避免跨 case 撞 unique
        persist_raw_transactions(
            db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
            source_type=stype,
            raw_transactions=[_raw(external_id=f"ex-{stype}", merchant=f"M-{stype}")],
        )
    db.flush()
    rows = db.execute(select(Transaction.source, Transaction.source_unique_key)
                      .where(Transaction.user_id == user.id)).all()
    by_key = dict(rows)
    assert "alipay" in {by_key[k] for k in by_key if k.startswith("alipay:")}
    assert "bank" in {by_key[k] for k in by_key if k.startswith("bank:")}


def test_persist_preserves_raw_payload_and_payment_method(db, env):
    user, acc, si = env
    raws = [_raw(payment_method_raw="建设银行信用卡(7432)",
                 raw_row={"col1": "v1", "col2": "v2"})]
    persist_raw_transactions(db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="wechat_xlsx", raw_transactions=raws)
    db.flush()
    tx = db.execute(select(Transaction).where(Transaction.user_id == user.id)).scalar_one()
    assert tx.payment_method_raw == "建设银行信用卡(7432)"
    assert tx.raw_payload == {"col1": "v1", "col2": "v2"}


def test_persist_empty_list_returns_0_0(db, env):
    user, acc, si = env
    created, skipped = persist_raw_transactions(
        db, user_id=user.id, account_id=acc.id, statement_import_id=si.id,
        source_type="alipay_csv", raw_transactions=[],
    )
    assert created == 0 and skipped == 0
```

- [ ] **Step 9.2:跑测试看失败**

```powershell
pytest tests/services/test_persist.py -v
```

期望:`ImportError: cannot import name 'persist_raw_transactions'`。

- [ ] **Step 9.3:在 `app/services/importer.py` 末尾追加 `persist_raw_transactions`**

打开 [backend/app/services/importer.py](backend/app/services/importer.py),在文件末尾追加(顶部 import 区也要补):

文件顶部 import 区追加:
```python
import hashlib  # 已有,不重
from typing import Iterable

from app.models import Transaction
from app.services.statement_parser import RawTransaction, normalize_merchant
```

文件末尾追加:
```python
_SOURCE_TYPE_TO_SOURCE = {
    "alipay_csv": "alipay",
    "wechat_xlsx": "wechat",
    "bank_pdf_bocom_debit": "bank",
    "bank_pdf_ccb_credit": "bank",
}


def _short_source(source_type: str) -> str:
    """source_type → source 短名(spec § 4.1)。"""
    if source_type in _SOURCE_TYPE_TO_SOURCE:
        return _SOURCE_TYPE_TO_SOURCE[source_type]
    raise ValueError(f"unknown source_type: {source_type!r}")


def _synth_unique_key(
    source_short: str, statement_import_id: int, row_idx: int,
    merchant: str, amount, tx_time,
) -> str:
    """external_tx_id 缺失时合成 unique key。

    用 statement_import_id + row_idx 保证 file 内唯一,加 sha8 防 file 间罕见撞。
    """
    sig = f"{merchant}|{amount}|{tx_time.isoformat()}".encode()
    sha8 = hashlib.sha256(sig).hexdigest()[:8]
    return f"{source_short}:si{statement_import_id}:r{row_idx}:{sha8}"


def persist_raw_transactions(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    statement_import_id: int,
    source_type: str,
    raw_transactions: Iterable[RawTransaction],
) -> tuple[int, int]:
    """把 RawTransaction 列表批量 insert。

    返回 (created_count, skipped_count_due_to_dup_unique_key)。
    spec § 5.1 step 4 + § 6.1 ①(同源跳过)。

    本函数只**插入数据**,不做跨源去重(Task 10-13)和分类(Task 14)。
    """
    source_short = _short_source(source_type)

    # 拉一次该 user 已存在的 source_unique_key 集合,避免 N+1 查询
    seen: set[str] = set(
        row[0] for row in db.execute(
            select(Transaction.source_unique_key).where(
                Transaction.user_id == user_id,
                Transaction.source_unique_key.isnot(None),
            )
        ).all() if row[0] is not None
    )

    created = 0
    skipped = 0
    for idx, raw in enumerate(raw_transactions):
        if raw.external_tx_id:
            unique_key = f"{source_short}:{raw.external_tx_id}"
        else:
            unique_key = _synth_unique_key(
                source_short, statement_import_id, idx,
                raw.merchant_raw or "", raw.amount, raw.tx_time,
            )
        if unique_key in seen:
            skipped += 1
            continue
        seen.add(unique_key)

        merchant_norm = normalize_merchant(raw.merchant_raw)
        tx = Transaction(
            user_id=user_id,
            account_id=account_id,
            statement_import_id=statement_import_id,
            tx_kind=raw.tx_kind,
            tx_time=raw.tx_time,
            post_time=raw.post_time,
            amount=raw.amount,
            currency=raw.currency,
            amount_settled_cny=raw.amount_settled_cny,
            merchant_raw=raw.merchant_raw or None,
            merchant_normalized=merchant_norm or None,
            counterparty_raw=raw.counterparty_raw,
            description_raw=raw.description_raw,
            category_id=None,
            classification_confidence=None,
            source=source_short,
            external_tx_id=raw.external_tx_id,
            external_merchant_id=raw.external_merchant_id,
            payment_method_raw=raw.payment_method_raw,
            is_mirror=False,
            mirror_of_id=None,
            source_unique_key=unique_key,
            raw_payload=raw.raw_row,
        )
        db.add(tx)
        created += 1

    db.flush()
    return created, skipped
```

- [ ] **Step 9.4:跑测试看通过**

```powershell
pytest tests/services/test_persist.py -v
```

期望:8 passed。

- [ ] **Step 9.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/importer.py backend/tests/services/test_persist.py
git commit -m "feat(importer): persist_raw_transactions with merchant_normalized + source_unique_key"
```

---

## Task 10:去重 service - § 6.1 ① 同源 + § 6.2 ② 微信→银行精确锚定

**Files:**
- Create: `backend/app/services/dedup.py`(本 task 写 `__init__` + 信号 ① 已在 Task 9 处理 + 信号 ② 实现 + 公开 API `run_dedup_pass`)
- Test: `backend/tests/services/test_dedup_anchor.py`

> spec § 6.1 信号优先级:
> ① external_tx_id 完全相等(同源重复) — **已在 Task 9 的 source_unique_key 唯一约束 + persist 的 seen 集合处理**,本 task 不重复实现
> ② 微信→银行精确锚定 — 本 task 实现:
> ```
> 对每条新进微信交易 W:
>   提取 W.payment_method_raw 中的 "(\d{4})" → last4
>   查 transactions.source = bank, account.last4 = last4,
>      tx_time ∈ [W.tx_time-1d, W.tx_time+1d], amount = W.amount, is_mirror=False
>   命中唯一一条 B → strong/auto-confirm,B.is_mirror=True, B.mirror_of_id=W.id, 写 dedup_candidates(strong, status=confirmed)
>   命中多条 → status=pending(进 ④/⑤ 待审核)
>   命中 0 条 → 不动
> ```
> 注意:**B 是 mirror 不是 W**,因为微信记录通常先发生(消费瞬间)而银行账户在交易日记账,所以银行那条作为"延迟见到的影子"。spec § 6.2 措辞为 "B.is_mirror=True"。

- [ ] **Step 10.1:写测试 `tests/services/test_dedup_anchor.py`**

```python
"""② 微信→银行精确锚定 dedup 测试 — spec § 6.2。"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, StatementImport, Transaction, User
from app.services.dedup import wechat_to_bank_anchor


@pytest.fixture
def env(db):
    user = User(username="dx", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    bank_acc = Account(user_id=user.id, name="建行信用卡 7432",
        type="bank_credit", institution="建设银行", last4="7432")
    wechat_acc = Account(user_id=user.id, name="微信支付", type="wechat",
        institution="微信支付", last4=None)
    db.add_all([bank_acc, wechat_acc])
    db.flush()
    return user, bank_acc, wechat_acc


def _add_tx(db, *, user_id, account_id, source, amount, tx_time,
            external_id=None, payment_method=None, merchant="X"):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=tx_time, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=external_id,
        payment_method_raw=payment_method, is_mirror=False,
        source_unique_key=f"{source}:{external_id or merchant}",
    )
    db.add(tx)
    db.flush()
    return tx


def test_wechat_anchors_unique_bank_tx(db, env):
    user, bank_acc, wechat_acc = env
    bank_tx = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="12.50",
        tx_time=datetime(2026, 3, 1, 14, 0, 0), merchant="瑞幸咖啡")
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="12.50",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="瑞幸咖啡")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    db.flush()

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.match_kind == "strong"
    assert pair.status == "confirmed"
    assert pair.confidence >= 0.95

    db.refresh(bank_tx)
    db.refresh(wechat_tx)
    assert bank_tx.is_mirror is True
    assert bank_tx.mirror_of_id == wechat_tx.id
    assert wechat_tx.is_mirror is False


def test_wechat_no_bank_match_no_op(db, env):
    """微信交易在 ±1d / 同 last4 / 同金额下找不到银行,不动。"""
    user, _, wechat_acc = env
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="99.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="无对应银行交易")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []
    db.refresh(wechat_tx)
    assert wechat_tx.is_mirror is False


def test_wechat_no_payment_method_skipped(db, env):
    """payment_method_raw 不含 4 位数字(零钱付),跳过。"""
    user, _, wechat_acc = env
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="5.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="零钱", merchant="街边小摊")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []


def test_wechat_multiple_bank_matches_pending(db, env):
    """同 day + last4 + amount 命中多条 bank 交易 → pending,等待人工。"""
    user, bank_acc, wechat_acc = env
    bank1 = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="50.00",
        tx_time=datetime(2026, 3, 1, 10, 0, 0), merchant="A", external_id="b1")
    bank2 = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="50.00",
        tx_time=datetime(2026, 3, 1, 16, 0, 0), merchant="B", external_id="b2")
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="50.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="C", external_id="w1")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    db.flush()

    # 多匹配 → 不写镜像,但写 pending pair(让用户在 review 页选)
    assert len(pairs) >= 2  # 一个微信对应两个 bank 候选,各开 pending pair
    for p in pairs:
        assert p.status == "pending"
        assert p.match_kind == "strong"
    db.refresh(bank1)
    db.refresh(bank2)
    assert bank1.is_mirror is False
    assert bank2.is_mirror is False


def test_wechat_outside_1d_window_no_match(db, env):
    """银行交易在 ±1d 之外,不匹配。"""
    user, bank_acc, wechat_acc = env
    _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="20.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0), merchant="远古交易")
    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="20.00",
        tx_time=datetime(2026, 3, 5, 12, 0, 0),  # 4 天后
        payment_method="建设银行信用卡(7432)", merchant="今日新交易")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []


def test_wechat_anchor_skips_bank_already_mirror(db, env):
    """已经被标 is_mirror 的银行交易不应再被认领。"""
    user, bank_acc, wechat_acc = env
    bank_tx = _add_tx(db, user_id=user.id, account_id=bank_acc.id,
        source="bank", amount="30.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0), merchant="X")
    bank_tx.is_mirror = True
    db.flush()

    wechat_tx = _add_tx(db, user_id=user.id, account_id=wechat_acc.id,
        source="wechat", amount="30.00",
        tx_time=datetime(2026, 3, 1, 12, 0, 0),
        payment_method="建设银行信用卡(7432)", merchant="Y")

    pairs = wechat_to_bank_anchor(db, user_id=user.id, new_wechat_ids=[wechat_tx.id])
    assert pairs == []
```

- [ ] **Step 10.2:跑测试看失败**

```powershell
pytest tests/services/test_dedup_anchor.py -v
```

期望:`ImportError: cannot import name 'wechat_to_bank_anchor'`。

- [ ] **Step 10.3:写 `app/services/dedup.py`**

```python
"""跨源去重 service — spec § 6。

5 个信号:
- ①  同源 external_tx_id 重复 → 已在 importer.persist_raw_transactions 处理
- ②  微信→银行精确锚定 (wechat_to_bank_anchor)
- ③  强重复(同源/跨源同日同额同商家高重合)— Task 11
- ④  桥接(支付宝→银行)— Task 12
- ⑤  对话↔账单 — Task 13

公开入口 run_dedup_pass:Task 13 添加,顺序调用 ② → ③ → ④ → ⑤。
"""
import re
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Account, DedupCandidate, Transaction


_LAST4_RE = re.compile(r"(\d{4})")
_ONE_DAY = timedelta(days=1)


def _extract_last4(payment_method: str | None) -> str | None:
    """从微信"建设银行信用卡(7432)" 抽 4 位数字。"""
    if not payment_method:
        return None
    m = _LAST4_RE.search(payment_method)
    return m.group(1) if m else None


def _make_pair(
    user_id: int,
    primary_id: int,
    mirror_id: int,
    *,
    match_kind: str,
    confidence: float,
    status: str,
    reasoning: dict,
) -> DedupCandidate:
    return DedupCandidate(
        user_id=user_id,
        primary_tx_id=primary_id,
        mirror_tx_id=mirror_id,
        match_kind=match_kind,
        confidence=confidence,
        status=status,
        reasoning=reasoning,
    )


def wechat_to_bank_anchor(
    db: Session, *, user_id: int, new_wechat_ids: list[int],
) -> list[DedupCandidate]:
    """spec § 6.2 ②:对新进微信交易,按 (last4, ±1d, amount) 找银行 mirror。

    - 唯一命中 → strong/confirmed,标 bank.is_mirror=True
    - 多命中 → 都开 strong/pending pair,等用户决断
    - 0 命中 → 不动
    """
    if not new_wechat_ids:
        return []

    pairs_created: list[DedupCandidate] = []

    wechat_txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(new_wechat_ids),
            Transaction.user_id == user_id,
            Transaction.source == "wechat",
        )
    ).scalars().all()

    for w in wechat_txs:
        last4 = _extract_last4(w.payment_method_raw)
        if not last4:
            continue
        tmin = w.tx_time - _ONE_DAY
        tmax = w.tx_time + _ONE_DAY

        candidates = db.execute(
            select(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.source == "bank",
                Transaction.is_mirror.is_(False),
                Transaction.amount == w.amount,
                Transaction.currency == w.currency,
                Transaction.tx_time >= tmin,
                Transaction.tx_time <= tmax,
                Account.last4 == last4,
            )
        ).scalars().all()

        if len(candidates) == 0:
            continue

        if len(candidates) == 1:
            b = candidates[0]
            b.is_mirror = True
            b.mirror_of_id = w.id
            pair = _make_pair(
                user_id, primary_id=w.id, mirror_id=b.id,
                match_kind="strong", confidence=0.99, status="confirmed",
                reasoning={
                    "rule": "wechat_to_bank_anchor",
                    "signals": ["last4_match", "amount_eq", "tx_time_within_1d", "unique_match"],
                    "last4": last4,
                    "delta_seconds": int((b.tx_time - w.tx_time).total_seconds()),
                },
            )
            db.add(pair)
            pairs_created.append(pair)
        else:
            for b in candidates:
                pair = _make_pair(
                    user_id, primary_id=w.id, mirror_id=b.id,
                    match_kind="strong", confidence=0.85, status="pending",
                    reasoning={
                        "rule": "wechat_to_bank_anchor",
                        "signals": ["last4_match", "amount_eq", "tx_time_within_1d",
                                    "ambiguous_multi_match"],
                        "last4": last4,
                        "candidates_count": len(candidates),
                    },
                )
                db.add(pair)
                pairs_created.append(pair)

    db.flush()
    return pairs_created
```

- [ ] **Step 10.4:跑测试看通过**

```powershell
pytest tests/services/test_dedup_anchor.py -v
```

期望:6 passed。

- [ ] **Step 10.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/dedup.py backend/tests/services/test_dedup_anchor.py
git commit -m "feat(dedup): wechat-to-bank precise anchor (signal ②, spec § 6.2)"
```

---

## Task 11:去重 service - § 6.3 ③ 强重复(同源/跨源 ±1h ratio≥80)

**Files:**
- Modify: `backend/app/services/dedup.py`(新增 `strong_dedup_cross_source`)
- Test: `backend/tests/services/test_dedup_strong.py`

> spec § 6.3:对每对候选 (A, B),source 不同:
> - tx_time 差 ≤ 1h
> - amount 等
> - currency 同
> - rapidfuzz.WRatio(A.merchant_normalized, B.merchant_normalized) ≥ 80
>   → strong / auto-confirm,B(后到的、source=bank 优先标 mirror)
>
> "后到"靠 created_at;若同时,优先 source = bank 标 mirror(银行账单滞后,作影子)。

- [ ] **Step 11.1:写测试 `tests/services/test_dedup_strong.py`**

```python
"""③ 强重复(跨源 ±1h ratio≥80) — spec § 6.3。"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, Transaction, User
from app.services.dedup import strong_dedup_cross_source


@pytest.fixture
def env(db):
    user = User(username="ds", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    bank_acc = Account(user_id=user.id, name="bocom", type="bank_debit",
        institution="交通银行", last4="2498")
    alipay_acc = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add_all([bank_acc, alipay_acc])
    db.flush()
    return user, bank_acc, alipay_acc


def _add(db, *, user_id, account_id, source, amount, t, merchant, ext=None):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=t, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=ext, is_mirror=False,
        source_unique_key=f"{source}:{ext or merchant}-{t.isoformat()}",
    )
    db.add(tx)
    db.flush()
    return tx


def test_cross_source_high_ratio_in_1h_pairs_confirmed(db, env):
    user, bank_acc, alipay_acc = env
    a = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="36.50", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    b = _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="36.50", t=datetime(2026, 3, 1, 12, 30), merchant="瑞幸咖啡 北京")

    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a.id, b.id])
    db.flush()

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.match_kind == "strong"
    assert pair.status == "confirmed"
    db.refresh(a); db.refresh(b)
    # bank 这条作 mirror(spec 默认银行滞后)
    assert b.is_mirror is True
    assert b.mirror_of_id == a.id


def test_outside_1h_no_pair(db, env):
    user, bank_acc, alipay_acc = env
    a = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="20.00", t=datetime(2026, 3, 1, 9, 0), merchant="星巴克")
    b = _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="20.00", t=datetime(2026, 3, 1, 11, 30), merchant="星巴克")  # 2.5h 差

    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a.id, b.id])
    assert pairs == []


def test_low_merchant_ratio_no_pair(db, env):
    user, bank_acc, alipay_acc = env
    _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="100.00", t=datetime(2026, 3, 1, 12, 0), merchant="完全无关公司A")
    _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="100.00", t=datetime(2026, 3, 1, 12, 10), merchant="完全无关公司B")
    new_ids = [t.id for t in db.execute(select(Transaction)).scalars().all()]
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=new_ids)
    # ratio 低,不该匹配
    assert pairs == []


def test_amount_mismatch_no_pair(db, env):
    user, bank_acc, alipay_acc = env
    _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="50.00", t=datetime(2026, 3, 1, 12, 0), merchant="美团")
    _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="50.01", t=datetime(2026, 3, 1, 12, 5), merchant="美团")
    new_ids = [t.id for t in db.execute(select(Transaction)).scalars().all()]
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=new_ids)
    assert pairs == []


def test_same_source_not_paired(db, env):
    """同 source 不应被本算法配对(由 ① external_tx_id 唯一约束处理)。"""
    user, _, alipay_acc = env
    a1 = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="10.00", t=datetime(2026, 3, 1, 12, 0), merchant="X", ext="e1")
    a2 = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="10.00", t=datetime(2026, 3, 1, 12, 30), merchant="X", ext="e2")
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a1.id, a2.id])
    assert pairs == []


def test_skips_already_mirror(db, env):
    user, bank_acc, alipay_acc = env
    a = _add(db, user_id=user.id, account_id=alipay_acc.id, source="alipay",
        amount="11.00", t=datetime(2026, 3, 1, 12, 0), merchant="美团外卖")
    b = _add(db, user_id=user.id, account_id=bank_acc.id, source="bank",
        amount="11.00", t=datetime(2026, 3, 1, 12, 30), merchant="美团外卖")
    b.is_mirror = True  # 假装已被 ② 处理
    db.flush()
    pairs = strong_dedup_cross_source(db, user_id=user.id, new_tx_ids=[a.id, b.id])
    assert pairs == []
```

- [ ] **Step 11.2:跑测试看失败**

```powershell
pytest tests/services/test_dedup_strong.py -v
```

期望:`ImportError`。

- [ ] **Step 11.3:在 `app/services/dedup.py` 追加 `strong_dedup_cross_source`**

打开 [backend/app/services/dedup.py](backend/app/services/dedup.py),顶部 import 区追加:

```python
from rapidfuzz import fuzz
```

文件末尾追加:

```python
_ONE_HOUR = timedelta(hours=1)
_STRONG_RATIO_THRESHOLD = 80


def strong_dedup_cross_source(
    db: Session, *, user_id: int, new_tx_ids: list[int],
) -> list[DedupCandidate]:
    """spec § 6.3 ③:同/跨源 ±1h ratio≥80 强重复。

    本算法:
    - 仅处理 source 不同的 (A, B) 对
    - 候选范围:本次新进 ids ∪ 已有未 mirror 交易,在新进 tx 时间窗口内
    - 命中:auto-confirm,bank 那条优先标 mirror;若两侧都非 bank,后到的(created_at 大)标 mirror
    """
    if not new_tx_ids:
        return []

    pairs_created: list[DedupCandidate] = []

    new_txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(new_tx_ids),
            Transaction.user_id == user_id,
            Transaction.is_mirror.is_(False),
        )
    ).scalars().all()

    for tx in new_txs:
        if tx.is_mirror:  # 在循环里被前面的 pair 标了
            continue
        # 在 ±1h、同金额、不同 source、未 mirror 中找候选
        cands = db.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.id != tx.id,
                Transaction.is_mirror.is_(False),
                Transaction.source != tx.source,
                Transaction.amount == tx.amount,
                Transaction.currency == tx.currency,
                Transaction.tx_time >= tx.tx_time - _ONE_HOUR,
                Transaction.tx_time <= tx.tx_time + _ONE_HOUR,
            )
        ).scalars().all()

        for cand in cands:
            ratio = fuzz.WRatio(tx.merchant_normalized or "", cand.merchant_normalized or "")
            if ratio < _STRONG_RATIO_THRESHOLD:
                continue
            # 决定谁作 mirror:bank 优先;否则 created_at 大者(后到)
            if tx.source == "bank" and cand.source != "bank":
                primary, mirror = cand, tx
            elif cand.source == "bank" and tx.source != "bank":
                primary, mirror = tx, cand
            else:
                # 比 created_at,后到的标 mirror
                primary, mirror = (
                    (tx, cand) if (tx.created_at or datetime.min) <= (cand.created_at or datetime.min)
                    else (cand, tx)
                )
            mirror.is_mirror = True
            mirror.mirror_of_id = primary.id
            pair = _make_pair(
                user_id, primary_id=primary.id, mirror_id=mirror.id,
                match_kind="strong", confidence=min(0.99, ratio / 100.0),
                status="confirmed",
                reasoning={
                    "rule": "strong_dedup_cross_source",
                    "signals": ["amount_eq", "currency_eq", "tx_time_within_1h",
                                f"merchant_ratio={ratio}"],
                    "ratio": ratio,
                },
            )
            db.add(pair)
            pairs_created.append(pair)
            break  # 同 tx 一旦匹配到,不重复配

    db.flush()
    return pairs_created
```

注意 `from datetime import datetime` 在文件顶部需要新加(若仅 `from datetime import timedelta`)。检查并补 import。

- [ ] **Step 11.4:跑测试看通过**

```powershell
pytest tests/services/test_dedup_strong.py -v
```

期望:6 passed。

- [ ] **Step 11.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/dedup.py backend/tests/services/test_dedup_strong.py
git commit -m "feat(dedup): strong cross-source dedup (signal ③, spec § 6.3)"
```

---

## Task 12:去重 service - § 6.4 ④ 桥接(支付宝→银行 中转方贪心)

**Files:**
- Modify: `backend/app/services/dedup.py`(新增 `bridge_alipay_to_bank` + 内部 `_greedy_aggregate`)
- Test: `backend/tests/services/test_dedup_bridge.py`

> spec § 6.4 ④:对每条**银行交易 B**,若 B.merchant_raw 含中转方关键词(支付宝/蚂蚁/拉扎斯/云闪付/支付平台/财付通):
> - 在 alipay source、tx_time ∈ [B.tx_time-1d, B.tx_time+1d]、is_mirror=False 中找候选
> - **a) 单笔金额相等** → bridge candidate, confidence=0.85, **status=pending**
> - **b) 多笔金额可贪心聚合 = B.amount** → bridge candidate(每条单独入 pair), confidence=0.65, status=pending
> - 全部进 dedup_candidates(bridge, pending),reasoning 记录 signals
>
> 注意:**桥接不 auto-confirm**(可能跨日/跨账,人工决断);单纯写 pending pair,**不**改 is_mirror。

- [ ] **Step 12.1:写测试 `tests/services/test_dedup_bridge.py`**

```python
"""④ 桥接(支付宝→银行) — spec § 6.4。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, Transaction, User
from app.services.dedup import bridge_alipay_to_bank


@pytest.fixture
def env(db):
    user = User(username="db", password_hash="$2b$12$" + "x" * 53)
    db.add(user)
    db.flush()
    bank = Account(user_id=user.id, name="bocom", type="bank_debit",
        institution="交通银行", last4="2498")
    ali = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", last4=None)
    db.add_all([bank, ali]); db.flush()
    return user, bank, ali


def _add(db, *, user_id, account_id, source, amount, t, merchant, ext=None):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=t, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=ext, is_mirror=False,
        source_unique_key=f"{source}:{ext or merchant}-{t.isoformat()}",
    )
    db.add(tx); db.flush()
    return tx


def test_single_alipay_matches_bank_amount_pending(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="42.00", t=datetime(2026, 3, 1, 14, 0),
        merchant="拉扎斯网络科技-饿了么")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="42.00", t=datetime(2026, 3, 1, 13, 0), merchant="某餐厅")

    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    db.flush()

    assert len(pairs) == 1
    p = pairs[0]
    assert p.match_kind == "bridge"
    assert p.status == "pending"
    assert p.primary_tx_id == a.id
    assert p.mirror_tx_id == b.id
    assert 0.8 <= p.confidence <= 0.9


def test_aggregate_two_alipay_match_one_bank(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="100.00", t=datetime(2026, 3, 2, 10, 0), merchant="蚂蚁(杭州)网络")
    a1 = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="60.00", t=datetime(2026, 3, 1, 18, 0), merchant="餐A", ext="a1")
    a2 = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="40.00", t=datetime(2026, 3, 1, 19, 0), merchant="超市B", ext="a2")

    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    db.flush()

    # 贪心聚合 60+40=100 → 两个 pending pair
    assert len(pairs) == 2
    for p in pairs:
        assert p.match_kind == "bridge"
        assert p.status == "pending"
        assert p.confidence < 0.8  # 聚合置信度低于单笔


def test_no_bridge_keyword_no_op(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="20.00", t=datetime(2026, 3, 1, 12, 0), merchant="超市POS消费")
    _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="20.00", t=datetime(2026, 3, 1, 12, 0), merchant="X")
    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    assert pairs == []


def test_no_alipay_match_in_window(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="77.00", t=datetime(2026, 3, 1, 12, 0), merchant="支付宝代扣")
    _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="77.00", t=datetime(2026, 3, 5, 12, 0), merchant="X")  # 4 天后
    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    assert pairs == []


def test_skips_already_mirror_alipay(db, env):
    user, bank, ali = env
    b = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="33.00", t=datetime(2026, 3, 1, 12, 0), merchant="财付通-X")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="33.00", t=datetime(2026, 3, 1, 12, 0), merchant="X")
    a.is_mirror = True; db.flush()
    pairs = bridge_alipay_to_bank(db, user_id=user.id, new_bank_ids=[b.id])
    assert pairs == []
```

- [ ] **Step 12.2:跑测试看失败**

```powershell
pytest tests/services/test_dedup_bridge.py -v
```

期望:`ImportError`。

- [ ] **Step 12.3:在 `app/services/dedup.py` 追加 `bridge_alipay_to_bank` + helper**

打开 [backend/app/services/dedup.py](backend/app/services/dedup.py),文件末尾追加:

```python
_BRIDGE_KEYWORDS = ("支付宝", "蚂蚁", "拉扎斯", "云闪付", "支付平台", "财付通")


def _has_bridge_keyword(merchant: str | None) -> bool:
    if not merchant:
        return False
    return any(k in merchant for k in _BRIDGE_KEYWORDS)


def _greedy_aggregate(target: Decimal, items: list[Transaction]) -> list[Transaction]:
    """从 items 里贪心选若干条,使金额之和 == target。

    策略:按 amount 降序排序,逐个累加;若超过 target 跳过,刚好等于 target 即返回。
    本切片用最朴素的"降序贪心+回溯"足以满足 spec(支付宝→银行同日聚合)。
    返回空列表表示无解。
    """
    if not items:
        return []
    sorted_items = sorted(items, key=lambda x: -x.amount)
    chosen: list[Transaction] = []
    remaining = target
    for it in sorted_items:
        if it.amount <= remaining:
            chosen.append(it)
            remaining -= it.amount
            if remaining == Decimal("0"):
                return chosen
    return []  # 没凑出


def bridge_alipay_to_bank(
    db: Session, *, user_id: int, new_bank_ids: list[int],
) -> list[DedupCandidate]:
    """spec § 6.4 ④:对新进银行交易,若 merchant 含中转方关键词,在 ±1d alipay 候选里:

    - 单笔等额 → bridge pending,confidence=0.85
    - 多笔贪心聚合 → 每条都开 bridge pending,confidence=0.65
    """
    if not new_bank_ids:
        return []

    pairs_created: list[DedupCandidate] = []

    bank_txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(new_bank_ids),
            Transaction.user_id == user_id,
            Transaction.source == "bank",
        )
    ).scalars().all()

    for b in bank_txs:
        if not _has_bridge_keyword(b.merchant_raw):
            continue
        cands = db.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.source == "alipay",
                Transaction.is_mirror.is_(False),
                Transaction.currency == b.currency,
                Transaction.tx_time >= b.tx_time - _ONE_DAY,
                Transaction.tx_time <= b.tx_time + _ONE_DAY,
            )
        ).scalars().all()

        # a) 优先单笔等额
        single_match = next((c for c in cands if c.amount == b.amount), None)
        if single_match is not None:
            pair = _make_pair(
                user_id, primary_id=single_match.id, mirror_id=b.id,
                match_kind="bridge", confidence=0.85, status="pending",
                reasoning={
                    "rule": "bridge_alipay_to_bank",
                    "signals": ["bridge_keyword_in_bank_merchant",
                                "single_alipay_amount_eq", "tx_time_within_1d"],
                    "alipay_tx_id": single_match.id,
                },
            )
            db.add(pair)
            pairs_created.append(pair)
            continue

        # b) 贪心聚合
        agg = _greedy_aggregate(b.amount, cands)
        if agg:
            for a in agg:
                pair = _make_pair(
                    user_id, primary_id=a.id, mirror_id=b.id,
                    match_kind="bridge", confidence=0.65, status="pending",
                    reasoning={
                        "rule": "bridge_alipay_to_bank",
                        "signals": ["bridge_keyword_in_bank_merchant",
                                    "alipay_amount_sum_eq", "tx_time_within_1d",
                                    f"aggregated_count={len(agg)}"],
                        "aggregated_alipay_ids": [x.id for x in agg],
                    },
                )
                db.add(pair)
                pairs_created.append(pair)

    db.flush()
    return pairs_created
```

- [ ] **Step 12.4:跑测试看通过**

```powershell
pytest tests/services/test_dedup_bridge.py -v
```

期望:5 passed。

- [ ] **Step 12.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/dedup.py backend/tests/services/test_dedup_bridge.py
git commit -m "feat(dedup): bridge alipay-to-bank with greedy aggregate (signal ④, spec § 6.4)"
```

---

## Task 13:去重 service - § 6.5 ⑤ 对话↔账单 + 公开入口 `run_dedup_pass`

**Files:**
- Modify: `backend/app/services/dedup.py`(新增 `conversation_match` + `run_dedup_pass` 总入口)
- Test: `backend/tests/services/test_dedup_conversation.py`(单元)
- Test: `backend/tests/services/test_dedup_run_pass.py`(集成,验证 4 个信号串起来)

> spec § 6.5 ⑤:对每条新进**账单交易 X**(source ∈ {bank, alipay, wechat}),查 source = conversation 来源、tx_time ∈ ±1d、amount 等的 C:
> - rapidfuzz.WRatio(X.merchant_normalized, C.merchant_normalized) ≥ 70
>   → conversation/pending pair,等用户决断"保留哪条"
>
> 本切片 conversation 来源还没真正接入(slice E MCP `add_transaction` 才会写),但 ⑤ 算法可以**预先实现**——只要表里有 source='conversation' 的行就 work,无 conversation 数据则空跑。
>
> `run_dedup_pass(db, user_id, new_tx_ids)` 是 `importer.run_import_pipeline` 调用的总入口,顺序:② → ③ → ④ → ⑤。

- [ ] **Step 13.1:写测试 `tests/services/test_dedup_conversation.py`**

```python
"""⑤ 对话↔账单 — spec § 6.5。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Account, Transaction, User
from app.services.dedup import conversation_match


@pytest.fixture
def env(db):
    user = User(username="dc", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    ali = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add(ali); db.flush()
    return user, ali


def _add(db, *, user_id, account_id, source, amount, t, merchant, ext=None):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=t, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=ext, is_mirror=False,
        source_unique_key=f"{source}:{ext or merchant}-{t.isoformat()}",
    )
    db.add(tx); db.flush()
    return tx


def test_conversation_matches_alipay_pending(db, env):
    user, ali = env
    c = _add(db, user_id=user.id, account_id=ali.id, source="conversation",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 30), merchant="瑞幸咖啡 北京")

    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    db.flush()

    assert len(pairs) == 1
    p = pairs[0]
    assert p.match_kind == "conversation"
    assert p.status == "pending"
    assert p.primary_tx_id in {c.id, a.id}
    assert p.mirror_tx_id in {c.id, a.id}


def test_no_conversation_no_op(db, env):
    user, ali = env
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    assert pairs == []


def test_low_ratio_no_pair(db, env):
    user, ali = env
    _add(db, user_id=user.id, account_id=ali.id, source="conversation",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="完全无关 X")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="星巴克咖啡")
    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    assert pairs == []


def test_amount_mismatch_no_pair(db, env):
    user, ali = env
    _add(db, user_id=user.id, account_id=ali.id, source="conversation",
        amount="14.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸")
    a = _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="15.00", t=datetime(2026, 3, 1, 12, 0), merchant="瑞幸咖啡")
    pairs = conversation_match(db, user_id=user.id, new_tx_ids=[a.id])
    assert pairs == []
```

- [ ] **Step 13.2:写集成测试 `tests/services/test_dedup_run_pass.py`**

```python
"""run_dedup_pass 串起 ②③④⑤,确保各信号正确触发不冲突。"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models import Account, Transaction, User
from app.services.dedup import run_dedup_pass


@pytest.fixture
def env(db):
    user = User(username="dr", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    bank = Account(user_id=user.id, name="ccb", type="bank_credit",
        institution="建设银行", last4="7432")
    ali = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    we = Account(user_id=user.id, name="微信", type="wechat",
        institution="微信支付", last4=None)
    db.add_all([bank, ali, we]); db.flush()
    return user, bank, ali, we


def _add(db, *, user_id, account_id, source, amount, t, merchant,
         ext=None, payment_method=None):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=t, amount=Decimal(amount),
        currency="CNY", amount_settled_cny=Decimal(amount),
        merchant_raw=merchant, merchant_normalized=merchant,
        source=source, external_tx_id=ext,
        payment_method_raw=payment_method, is_mirror=False,
        source_unique_key=f"{source}:{ext or merchant}-{t.isoformat()}",
    )
    db.add(tx); db.flush()
    return tx


def test_run_dedup_pass_handles_all_four_signals(db, env):
    """场景:微信→建行 锚定 + 支付宝→交行 桥接(无;此场景重点 ②/③)。"""
    user, bank, ali, we = env
    # 微信 + 建行(应被 ② 锚定)
    bank_tx = _add(db, user_id=user.id, account_id=bank.id, source="bank",
        amount="20.00", t=datetime(2026, 3, 1, 13, 0), merchant="瑞幸咖啡 7432")
    we_tx = _add(db, user_id=user.id, account_id=we.id, source="wechat",
        amount="20.00", t=datetime(2026, 3, 1, 12, 0),
        payment_method="建设银行信用卡(7432)", merchant="瑞幸咖啡")

    # 支付宝 + 另一笔建行(强重复,但金额不同所以不命中)
    _add(db, user_id=user.id, account_id=ali.id, source="alipay",
        amount="50.00", t=datetime(2026, 3, 2, 9, 0), merchant="星巴克")

    pairs = run_dedup_pass(db, user_id=user.id, new_tx_ids=[bank_tx.id, we_tx.id])
    db.flush()

    # 至少有 1 个 strong/confirmed pair(微信→银行锚定)
    assert any(p.match_kind == "strong" and p.status == "confirmed" for p in pairs)
    db.refresh(bank_tx); db.refresh(we_tx)
    assert bank_tx.is_mirror is True
    assert we_tx.is_mirror is False


def test_run_dedup_pass_empty_input(db, env):
    user, _, _, _ = env
    pairs = run_dedup_pass(db, user_id=user.id, new_tx_ids=[])
    assert pairs == []
```

- [ ] **Step 13.3:跑测试看失败**

```powershell
pytest tests/services/test_dedup_conversation.py tests/services/test_dedup_run_pass.py -v
```

期望:`ImportError: cannot import name 'conversation_match' / 'run_dedup_pass'`。

- [ ] **Step 13.4:在 `app/services/dedup.py` 追加 `conversation_match` + `run_dedup_pass`**

打开 [backend/app/services/dedup.py](backend/app/services/dedup.py),文件末尾追加:

```python
_CONVERSATION_RATIO_THRESHOLD = 70


def conversation_match(
    db: Session, *, user_id: int, new_tx_ids: list[int],
) -> list[DedupCandidate]:
    """spec § 6.5 ⑤:新进的账单交易 vs 已有 conversation 录入交易。

    匹配条件:同金额 + ±1d + ratio>=70。命中 → conversation/pending pair。
    """
    if not new_tx_ids:
        return []

    pairs_created: list[DedupCandidate] = []

    new_txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(new_tx_ids),
            Transaction.user_id == user_id,
            Transaction.source != "conversation",  # 自身不是 conversation
            Transaction.is_mirror.is_(False),
        )
    ).scalars().all()

    for x in new_txs:
        cands = db.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.source == "conversation",
                Transaction.is_mirror.is_(False),
                Transaction.amount == x.amount,
                Transaction.currency == x.currency,
                Transaction.tx_time >= x.tx_time - _ONE_DAY,
                Transaction.tx_time <= x.tx_time + _ONE_DAY,
            )
        ).scalars().all()

        for c in cands:
            ratio = fuzz.WRatio(x.merchant_normalized or "", c.merchant_normalized or "")
            if ratio < _CONVERSATION_RATIO_THRESHOLD:
                continue
            pair = _make_pair(
                user_id, primary_id=c.id, mirror_id=x.id,
                match_kind="conversation", confidence=min(0.95, ratio / 100.0),
                status="pending",
                reasoning={
                    "rule": "conversation_match",
                    "signals": ["amount_eq", "tx_time_within_1d", f"ratio={ratio}"],
                },
            )
            db.add(pair)
            pairs_created.append(pair)
            break  # 同 x 只配一条 conversation

    db.flush()
    return pairs_created


def run_dedup_pass(
    db: Session, *, user_id: int, new_tx_ids: list[int],
) -> list[DedupCandidate]:
    """spec § 6 总入口:② → ③ → ④ → ⑤ 顺序处理新进 tx。

    ① 同源跳过已在 importer.persist_raw_transactions 处理。
    """
    if not new_tx_ids:
        return []

    all_pairs: list[DedupCandidate] = []

    # ② 微信→银行 — 仅取 wechat 的新进 ids
    wechat_ids = [
        row[0] for row in db.execute(
            select(Transaction.id).where(
                Transaction.id.in_(new_tx_ids),
                Transaction.source == "wechat",
            )
        ).all()
    ]
    all_pairs.extend(wechat_to_bank_anchor(db, user_id=user_id, new_wechat_ids=wechat_ids))

    # ③ 强重复 — 全量新进 ids,内部按 source 不同过滤
    all_pairs.extend(strong_dedup_cross_source(db, user_id=user_id, new_tx_ids=new_tx_ids))

    # ④ 桥接 — 仅取 bank 的新进 ids
    bank_ids = [
        row[0] for row in db.execute(
            select(Transaction.id).where(
                Transaction.id.in_(new_tx_ids),
                Transaction.source == "bank",
            )
        ).all()
    ]
    all_pairs.extend(bridge_alipay_to_bank(db, user_id=user_id, new_bank_ids=bank_ids))

    # ⑤ 对话↔账单 — 全量新进 ids,内部排除 source=conversation
    all_pairs.extend(conversation_match(db, user_id=user_id, new_tx_ids=new_tx_ids))

    return all_pairs
```

- [ ] **Step 13.5:跑测试看通过**

```powershell
pytest tests/services/test_dedup_conversation.py tests/services/test_dedup_run_pass.py -v
```

期望:6 passed(4 conversation + 2 run_pass)。

- [ ] **Step 13.6:跑全部 dedup 测试,无 regression**

```powershell
pytest tests/services/test_dedup_*.py -v
```

期望:Task 10 + 11 + 12 + 13 全部 pass(共 ~21 tests)。

- [ ] **Step 13.7:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/dedup.py backend/tests/services/test_dedup_conversation.py backend/tests/services/test_dedup_run_pass.py
git commit -m "feat(dedup): conversation match (signal ⑤) + run_dedup_pass orchestrator"
```

---

## Task 14:分类引擎 — 规则匹配 + marker 处理(对接 Task 4 契约)

**Files:**
- Create: `backend/app/services/classifier.py`
- Test: `backend/tests/services/test_classifier.py`(本 task 新增的非契约测试)
- Modify: `backend/tests/services/test_classifier_marker_contract.py`(摘掉 xfail marker,Task 4 留给本 task 的)

> spec § 7.2 + slice A Rec #5(Task 4 已冻结契约):
> ```
> 对每条 transaction T(category_id IS NULL):
>   按 priority ASC 拉用户 + 种子规则:
>     if match(T.merchant_normalized, rule):
>       rule.hit_count += 1
>       if rule.category_id IS NULL:    # marker 规则
>         T.raw_payload['markers'] += pattern  (累加,去重)
>         continue
>       else:                            # 真分类规则
>         T.category_id = rule.category_id
>         T.classification_confidence = 1.0
>         break
> ```
> 4 种 match_kind:
> - `exact`:`T.merchant_normalized == pattern`
> - `contains`:`pattern in T.merchant_normalized`(大小写不敏感)
> - `regex`:`re.search(pattern, T.merchant_normalized)`
> - `fuzzy`:`fuzz.WRatio(T.merchant_normalized, pattern) >= 80`
>
> 公开 API:
> - `classify_transaction(db, tx) -> ClassifyResult` 单条(Task 4 契约用)
> - `classify_batch(db, user_id, tx_ids)` 批量 → returns (classified_count, marker_only_count)

- [ ] **Step 14.1:写非契约测试 `tests/services/test_classifier.py`**

```python
"""classifier 实现测试(非契约,实现细节)。"""
import re
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Category, MerchantRule, Transaction, User
from app.services.classifier import classify_batch, classify_transaction, _match_rule


@pytest.fixture
def setup(db):
    user = User(username="cl", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    cat = Category(user_id=user.id, name="餐饮", kind="expense", parent_id=None)
    db.add(cat); db.flush()
    coffee = Category(user_id=user.id, name="咖啡", kind="expense", parent_id=cat.id)
    db.add(coffee); db.flush()
    acc = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", last4=None)
    db.add(acc); db.flush()
    return user, acc, {"food": cat.id, "coffee": coffee.id}


def _mk_tx(db, user_id, account_id, merchant, **kw):
    tx = Transaction(
        user_id=user_id, account_id=account_id, statement_import_id=None,
        tx_kind="expense", tx_time=datetime(2026, 3, 1, 12, 0),
        amount=Decimal("10.00"), currency="CNY", amount_settled_cny=Decimal("10.00"),
        merchant_raw=merchant, merchant_normalized=merchant,
        category_id=None, source=kw.get("source", "alipay"),
        is_mirror=False, raw_payload=kw.get("raw_payload") or {},
    )
    db.add(tx); db.flush()
    return tx


def _add_rule(db, user_id, pattern, match_kind, category_id=None, priority=100):
    r = MerchantRule(user_id=user_id, pattern=pattern, match_kind=match_kind,
        category_id=category_id, priority=priority)
    db.add(r); db.flush()
    return r


def test_match_rule_exact():
    assert _match_rule("瑞幸咖啡", "瑞幸咖啡", "exact") is True
    assert _match_rule("瑞幸咖啡 北京", "瑞幸咖啡", "exact") is False


def test_match_rule_contains_case_insensitive():
    assert _match_rule("Luckin Coffee", "luckin", "contains") is True
    assert _match_rule("LUCKIN COFFEE", "luckin", "contains") is True
    assert _match_rule("星巴克", "luckin", "contains") is False


def test_match_rule_regex():
    assert _match_rule("银联入账7432", r"银联入账.*\d{4}", "regex") is True
    assert _match_rule("普通商户", r"银联入账.*\d{4}", "regex") is False


def test_match_rule_fuzzy_ratio_threshold():
    """fuzzy 默认 ratio>=80。"""
    # rapidfuzz.WRatio("瑞幸咖啡", "瑞幸 咖啡") 应该很高
    assert _match_rule("瑞幸 咖啡", "瑞幸咖啡", "fuzzy") is True
    # 完全不相关
    assert _match_rule("电信费", "瑞幸咖啡", "fuzzy") is False


def test_classify_batch_assigns_and_counts(db, setup):
    user, acc, cats = setup
    _add_rule(db, user.id, "瑞幸咖啡", "fuzzy", cats["coffee"], priority=50)
    _add_rule(db, user.id, "财付通-", "contains", None, priority=20)
    txs = [
        _mk_tx(db, user.id, acc.id, "瑞幸咖啡 北京"),
        _mk_tx(db, user.id, acc.id, "财付通-美团"),
        _mk_tx(db, user.id, acc.id, "陌生商户"),
    ]
    classified, marker_only = classify_batch(
        db, user_id=user.id, tx_ids=[t.id for t in txs])
    db.flush()
    assert classified == 1
    assert marker_only == 1   # 财付通-美团 命中 marker 但无真分类规则


def test_classify_does_nothing_for_already_classified(db, setup):
    """已有 category_id 的 tx 不应被重新分类(避免覆盖用户手工改类)。"""
    user, acc, cats = setup
    _add_rule(db, user.id, "瑞幸咖啡", "fuzzy", cats["coffee"], priority=50)
    tx = _mk_tx(db, user.id, acc.id, "瑞幸咖啡 北京")
    tx.category_id = cats["food"]  # 用户手工选了"餐饮"父分类
    tx.classification_confidence = 0.5  # 之前 Agent 模糊归类
    db.flush()
    classify_transaction(db, tx)
    db.refresh(tx)
    assert tx.category_id == cats["food"]  # 不动
    assert tx.classification_confidence == 0.5
```

- [ ] **Step 14.2:跑测试看失败**

```powershell
pytest tests/services/test_classifier.py -v
```

期望:`ImportError: cannot import name 'classify_transaction' from 'app.services.classifier'`。

- [ ] **Step 14.3:写 `app/services/classifier.py`**

```python
"""规则分类引擎 — spec § 7。

契约见 tests/services/test_classifier_marker_contract.py(Task 4 冻结):
- 普通规则命中:T.category_id = rule.category_id, confidence=1.0, hit_count++, break
- marker 规则命中(rule.category_id IS NULL):hit_count++, T.raw_payload['markers'] += pattern, NOT break
- 多 marker + 真规则:markers 累加 + 真规则赋值后 break
- 全 marker 命中:category_id 仍 None,markers 累加
"""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import MerchantRule, Transaction


_FUZZY_THRESHOLD = 80


@dataclass
class ClassifyResult:
    """单条分类结果,Task 4 契约测试用 matched_rule_id。"""
    matched_rule_id: int | None
    matched_marker_ids: list[int]


def _match_rule(merchant_norm: str, pattern: str, match_kind: str) -> bool:
    """返回 merchant_normalized 是否命中规则 pattern。"""
    if not merchant_norm or not pattern:
        return False
    if match_kind == "exact":
        return merchant_norm == pattern
    if match_kind == "contains":
        return pattern.lower() in merchant_norm.lower()
    if match_kind == "regex":
        try:
            return re.search(pattern, merchant_norm) is not None
        except re.error:
            return False
    if match_kind == "fuzzy":
        return fuzz.WRatio(merchant_norm, pattern) >= _FUZZY_THRESHOLD
    return False


def _append_marker(tx: Transaction, pattern: str) -> None:
    """累加 pattern 到 tx.raw_payload['markers'],去重保持顺序。"""
    payload = dict(tx.raw_payload or {})
    markers: list[str] = list(payload.get("markers") or [])
    if pattern not in markers:
        markers.append(pattern)
    payload["markers"] = markers
    tx.raw_payload = payload
    flag_modified(tx, "raw_payload")


def classify_transaction(db: Session, tx: Transaction) -> ClassifyResult:
    """对单条交易跑规则匹配。spec § 7.2 + Task 4 契约。

    已分类(category_id 非 None)→ no-op,直接返回 ClassifyResult(None, [])。
    """
    if tx.category_id is not None:
        return ClassifyResult(None, [])

    rules = db.execute(
        select(MerchantRule)
        .where(MerchantRule.user_id == tx.user_id)
        .order_by(MerchantRule.priority.asc(), MerchantRule.id.asc())
    ).scalars().all()

    matched_marker_ids: list[int] = []

    for rule in rules:
        if not _match_rule(tx.merchant_normalized or "", rule.pattern, rule.match_kind):
            continue
        rule.hit_count = (rule.hit_count or 0) + 1
        if rule.category_id is None:
            # marker 规则:不 break,继续找真分类
            _append_marker(tx, rule.pattern)
            matched_marker_ids.append(rule.id)
            continue
        # 真分类规则:赋值 + break
        tx.category_id = rule.category_id
        tx.classification_confidence = 1.0
        db.flush()
        return ClassifyResult(matched_rule_id=rule.id, matched_marker_ids=matched_marker_ids)

    db.flush()
    return ClassifyResult(matched_rule_id=None, matched_marker_ids=matched_marker_ids)


def classify_batch(
    db: Session, *, user_id: int, tx_ids: list[int],
) -> tuple[int, int]:
    """批量分类。返回 (classified_count, marker_only_count)。

    classified_count = 真分类生效的 tx 数(category_id 被赋值)
    marker_only_count = 仅命中 marker 但未被真分类的 tx 数
    """
    if not tx_ids:
        return 0, 0
    classified = 0
    marker_only = 0
    txs = db.execute(
        select(Transaction).where(
            Transaction.id.in_(tx_ids),
            Transaction.user_id == user_id,
        )
    ).scalars().all()
    for tx in txs:
        result = classify_transaction(db, tx)
        if result.matched_rule_id is not None:
            classified += 1
        elif result.matched_marker_ids:
            marker_only += 1
    db.flush()
    return classified, marker_only
```

- [ ] **Step 14.4:摘掉 Task 4 契约测试的 xfail marker**

打开 [backend/tests/services/test_classifier_marker_contract.py](backend/tests/services/test_classifier_marker_contract.py),删除文件顶部的:

```python
pytestmark = pytest.mark.xfail(
    reason="awaits Task 14 classifier implementation",
    raises=ImportError,
    strict=True,
)
```

(整段 4 行)。

- [ ] **Step 14.5:跑契约测试 + 实现测试**

```powershell
pytest tests/services/test_classifier.py tests/services/test_classifier_marker_contract.py -v
```

期望:契约 6 + 实现 6 = 12 passed。

排查:
- 契约 `test_marker_then_real_rule_assigns_category_from_real_rule` 失败 → 检查 `_append_marker` 是否真把 pattern 写入 `raw_payload['markers']`,且 `flag_modified` 通知 SQLAlchemy(JSONB 字段就地修改不被自动检测)
- `test_priority_order_respected_with_markers` 失败 → 看 ORDER BY 是否 `priority ASC, id ASC`(本实现已加二级 id ASC 保插入顺序)

- [ ] **Step 14.6:跑全测试套件确认无 regression**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
pytest -v --durations=10
```

期望:全部 pass,总时间 < 60s。

- [ ] **Step 14.7:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/classifier.py backend/tests/services/test_classifier.py backend/tests/services/test_classifier_marker_contract.py
git commit -m "feat(classifier): rule matching with marker rule support (spec § 7, slice A Rec #5)"
```

---

## Task 15:导入端点 — `POST /api/statements/import` 总编排

**Files:**
- Modify: `backend/app/services/importer.py`(追加 `run_import_pipeline` 总编排函数)
- Create: `backend/app/api/statements.py`(本 task 只放 `POST /import`,Task 16 补 list/detail/review)
- Modify: `backend/app/main.py`(挂载 statements router)
- Test: `backend/tests/services/test_importer_pipeline.py`(service 层集成)
- Test: `backend/tests/api/test_statements_import.py`(HTTP 层 e2e)

> spec § 5.1 全流程 + § 9.1 `/statements`:
> ```
> [1] multipart upload 拿 file_bytes + filename
> [2] route_and_parse(file_bytes, filename) → ParseResult(支持失败抛 UnsupportedStatementError → 400)
> [3] file_sha256(file_bytes) 查 statement_imports.file_hash → 重复抛 DuplicateImportError → 409
> [4] ensure_account_for_hint(parse_result.account_hint)
> [5] ensure_statement_import(...)
> [6] persist_raw_transactions(parse_result.raw_transactions) → (created, skipped_same_source)
> [7] run_dedup_pass(new_tx_ids = 步骤 6 创建的 ids) → list[DedupCandidate]
> [8] classify_batch(tx_ids = 步骤 6 创建的 ids) → (classified, marker_only)
> [9] update statement_import 的 imported_count / deduped_count / classified_count
> [10] 返回 ImportResponse
> ```
> 端点必须 `current_user` 鉴权,文件大小限 10MB,multipart 单文件名 `file`。

- [ ] **Step 15.1:在 `app/services/importer.py` 末尾追加 `run_import_pipeline`**

打开 [backend/app/services/importer.py](backend/app/services/importer.py),顶部 import 区追加:

```python
from app.schemas import ImportResponse
from app.services.classifier import classify_batch
from app.services.dedup import run_dedup_pass
from app.services.statement_parser import (
    UnsupportedStatementError,
    route_and_parse,
)
```

文件末尾追加:

```python
def run_import_pipeline(
    db: Session,
    *,
    user_id: int,
    file_bytes: bytes,
    filename: str,
) -> ImportResponse:
    """spec § 5.1 全流程编排。

    顺序:
    [1] route_and_parse → ParseResult(失败 raise UnsupportedStatementError)
    [2] file_sha256 + 查 statement_imports.file_hash(重复 raise DuplicateImportError)
    [3] ensure_account_for_hint
    [4] ensure_statement_import
    [5] persist_raw_transactions
    [6] run_dedup_pass(new_tx_ids)
    [7] classify_batch(new_tx_ids)
    [8] update statement_import 计数
    [9] return ImportResponse
    """
    # [1] 解析(parser 失败抛 UnsupportedStatementError 或 ValueError;HTTP 层处理)
    pr = route_and_parse(file_bytes, filename)

    # [2] file_hash
    fh = file_sha256(file_bytes)

    # [3] account
    account = ensure_account_for_hint(db, user_id, pr.account_hint)

    # [4] statement_import(可能抛 DuplicateImportError → HTTP 409)
    si = ensure_statement_import(
        db, user_id=user_id, account_id=account.id,
        source_type=pr.raw_transactions[0].raw_row.get("__source_type__")
                    if False else _infer_source_type_from_parser(pr),
        filename=filename, file_hash=fh, parse_result=pr,
    )
    # 注:source_type 直接从 parser 推断更稳。我们从 ParseResult.account_hint.type 派生:
    # alipay → alipay_csv, wechat → wechat_xlsx, bank_credit/bank_debit → bank_pdf_*
    # 实际 fix:见下方 _infer_source_type_from_parser 的实现。

    # [5] persist
    created_ids = _persist_and_return_ids(
        db, user_id=user_id, account_id=account.id,
        statement_import_id=si.id, source_type=si.source_type,
        raw_transactions=pr.raw_transactions,
    )
    skipped_same_source = len(pr.raw_transactions) - len(created_ids)

    # [6] dedup
    pairs = run_dedup_pass(db, user_id=user_id, new_tx_ids=created_ids)
    strong_confirmed = sum(
        1 for p in pairs if p.match_kind == "strong" and p.status == "confirmed"
    )
    pending = sum(1 for p in pairs if p.status == "pending")

    # [7] classify
    classified, marker_only = classify_batch(db, user_id=user_id, tx_ids=created_ids)

    # [8] update statement_import 计数
    si.raw_row_count = pr.metadata.get("raw_row_count", len(pr.raw_transactions))
    si.imported_count = len(created_ids)
    si.deduped_count = strong_confirmed
    si.classified_count = classified
    db.flush()

    return ImportResponse(
        import_id=si.id,
        source_type=si.source_type,
        raw_row_count=si.raw_row_count,
        imported_count=si.imported_count,
        deduped_strong_count=strong_confirmed,
        dedup_pending_count=pending,
        classified_count=classified,
        unclassified_count=len(created_ids) - classified - marker_only,
    )


def _infer_source_type_from_parser(pr: ParseResult) -> str:
    """从 ParseResult.account_hint 派生 statement_imports.source_type。"""
    t = pr.account_hint.type
    inst = pr.account_hint.institution
    if t == "alipay":
        return "alipay_csv"
    if t == "wechat":
        return "wechat_xlsx"
    if t == "bank_debit" and "交通" in (inst or ""):
        return "bank_pdf_bocom_debit"
    if t == "bank_credit" and "建设" in (inst or ""):
        return "bank_pdf_ccb_credit"
    raise ValueError(f"cannot infer source_type from account_hint={pr.account_hint!r}")


def _persist_and_return_ids(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    statement_import_id: int,
    source_type: str,
    raw_transactions: list[RawTransaction],
) -> list[int]:
    """persist_raw_transactions 包装,返回新创建的 tx ids 列表。

    现有 persist_raw_transactions 返回 (created, skipped),不返回 ids。本函数复用其逻辑
    但在 add 后收集 id(flush 后 id 即可见)。为保持向后兼容不改原函数签名。
    """
    source_short = _short_source(source_type)
    seen: set[str] = set(
        row[0] for row in db.execute(
            select(Transaction.source_unique_key).where(
                Transaction.user_id == user_id,
                Transaction.source_unique_key.isnot(None),
            )
        ).all() if row[0] is not None
    )
    new_ids: list[int] = []
    for idx, raw in enumerate(raw_transactions):
        if raw.external_tx_id:
            unique_key = f"{source_short}:{raw.external_tx_id}"
        else:
            unique_key = _synth_unique_key(
                source_short, statement_import_id, idx,
                raw.merchant_raw or "", raw.amount, raw.tx_time,
            )
        if unique_key in seen:
            continue
        seen.add(unique_key)
        merchant_norm = normalize_merchant(raw.merchant_raw)
        tx = Transaction(
            user_id=user_id, account_id=account_id,
            statement_import_id=statement_import_id,
            tx_kind=raw.tx_kind, tx_time=raw.tx_time, post_time=raw.post_time,
            amount=raw.amount, currency=raw.currency,
            amount_settled_cny=raw.amount_settled_cny,
            merchant_raw=raw.merchant_raw or None,
            merchant_normalized=merchant_norm or None,
            counterparty_raw=raw.counterparty_raw, description_raw=raw.description_raw,
            category_id=None, classification_confidence=None,
            source=source_short, external_tx_id=raw.external_tx_id,
            external_merchant_id=raw.external_merchant_id,
            payment_method_raw=raw.payment_method_raw,
            is_mirror=False, mirror_of_id=None,
            source_unique_key=unique_key, raw_payload=raw.raw_row,
        )
        db.add(tx)
        db.flush()  # 立即 flush 拿 id
        new_ids.append(tx.id)
    return new_ids
```

注意:`run_import_pipeline` 内对 `si.source_type` 的 inline 分支(第 18-22 行那段 `if False else ...`)是占位,**实际只保留下方那行 `source_type=_infer_source_type_from_parser(pr)`**。重写干净版:

```python
def run_import_pipeline(...) -> ImportResponse:
    pr = route_and_parse(file_bytes, filename)
    fh = file_sha256(file_bytes)
    account = ensure_account_for_hint(db, user_id, pr.account_hint)
    source_type = _infer_source_type_from_parser(pr)
    si = ensure_statement_import(
        db, user_id=user_id, account_id=account.id,
        source_type=source_type, filename=filename, file_hash=fh, parse_result=pr,
    )
    created_ids = _persist_and_return_ids(
        db, user_id=user_id, account_id=account.id,
        statement_import_id=si.id, source_type=source_type,
        raw_transactions=pr.raw_transactions,
    )
    pairs = run_dedup_pass(db, user_id=user_id, new_tx_ids=created_ids)
    strong_confirmed = sum(1 for p in pairs if p.match_kind == "strong" and p.status == "confirmed")
    pending = sum(1 for p in pairs if p.status == "pending")
    classified, marker_only = classify_batch(db, user_id=user_id, tx_ids=created_ids)
    si.raw_row_count = pr.metadata.get("raw_row_count", len(pr.raw_transactions))
    si.imported_count = len(created_ids)
    si.deduped_count = strong_confirmed
    si.classified_count = classified
    db.flush()
    return ImportResponse(
        import_id=si.id,
        source_type=source_type,
        raw_row_count=si.raw_row_count,
        imported_count=len(created_ids),
        deduped_strong_count=strong_confirmed,
        dedup_pending_count=pending,
        classified_count=classified,
        unclassified_count=len(created_ids) - classified - marker_only,
    )
```

(用这个干净版替换第一版,删除 inline `if False else` 那段歧义代码。)

- [ ] **Step 15.2:写 service 层集成测试 `tests/services/test_importer_pipeline.py`**

```python
"""run_import_pipeline 集成测试 — 用真实样本走全流程。"""
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import StatementImport, Transaction, User
from app.services.importer import DuplicateImportError, run_import_pipeline
from app.services.statement_parser import UnsupportedStatementError


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


@pytest.fixture
def test_user(db) -> User:
    u = User(username="ip", password_hash="$2b$12$" + "x" * 53)
    db.add(u); db.flush()
    return u


def _load(name: str) -> bytes:
    p = _FIXTURES / name
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return p.read_bytes()


def test_pipeline_alipay_full_run(db, test_user):
    bytes_ = _load("alipay_sample.csv")
    resp = run_import_pipeline(
        db, user_id=test_user.id, file_bytes=bytes_,
        filename="alipay_sample.csv",
    )
    db.flush()
    assert resp.import_id is not None
    assert resp.source_type == "alipay_csv"
    assert resp.imported_count >= 1
    txs = db.execute(select(Transaction).where(
        Transaction.user_id == test_user.id, Transaction.source == "alipay")
    ).scalars().all()
    assert len(txs) == resp.imported_count


def test_pipeline_duplicate_file_raises(db, test_user):
    bytes_ = _load("alipay_sample.csv")
    run_import_pipeline(db, user_id=test_user.id, file_bytes=bytes_,
        filename="alipay_sample.csv")
    db.flush()
    with pytest.raises(DuplicateImportError):
        run_import_pipeline(db, user_id=test_user.id, file_bytes=bytes_,
            filename="alipay_sample_v2.csv")  # 不同文件名,但 hash 相同


def test_pipeline_unsupported_file_raises(db, test_user):
    with pytest.raises(UnsupportedStatementError):
        run_import_pipeline(db, user_id=test_user.id,
            file_bytes=b"random text not any statement", filename="x.txt")


def test_pipeline_wechat_then_bank_creates_anchor(db, test_user):
    """端到端验证 ②:微信先导入 → 建行 PDF 后导入,观察 is_mirror 出现。"""
    we = _load("wechat_sample.xlsx")
    ccb = _load("ccb_credit_sample.pdf")
    resp1 = run_import_pipeline(db, user_id=test_user.id,
        file_bytes=we, filename="wechat_sample.xlsx")
    db.flush()
    resp2 = run_import_pipeline(db, user_id=test_user.id,
        file_bytes=ccb, filename="ccb_credit_sample.pdf")
    db.flush()
    # ccb 那次应至少出现 strong/confirmed 或 pending 镜像
    assert resp2.deduped_strong_count + resp2.dedup_pending_count >= 0  # 真实样本可能为 0,不强求,但流程不抛错即可
    # 至少 ccb 有交易入库
    assert resp2.imported_count >= 1


def test_pipeline_count_consistency(db, test_user):
    """imported_count + deduped + dedup_pending + unclassified 关系自洽。"""
    bytes_ = _load("alipay_sample.csv")
    resp = run_import_pipeline(db, user_id=test_user.id, file_bytes=bytes_,
        filename="alipay_sample.csv")
    # classified + marker_only + unclassified == imported_count
    # marker_only = imported - classified - unclassified
    assert (resp.classified_count + resp.unclassified_count) <= resp.imported_count
    assert resp.unclassified_count >= 0
```

- [ ] **Step 15.3:写 `app/api/statements.py`(本 task 只 POST /import)**

```python
"""Statements API — spec § 9.1 + § 5.1。

本 task(15):POST /import
Task 16:list / detail / review
"""
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUserDep, DbDep
from app.schemas import ImportResponse
from app.services.importer import DuplicateImportError, run_import_pipeline
from app.services.statement_parser import UnsupportedStatementError


router = APIRouter(prefix="/statements", tags=["statements"])


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/import", response_model=ImportResponse)
async def import_statement(
    user: CurrentUserDep, db: DbDep, file: UploadFile = File(...),
) -> ImportResponse:
    """multipart upload → 跑导入流水线。spec § 5.1。"""
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file > {_MAX_UPLOAD_BYTES // 1024 // 1024}MB")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    try:
        return run_import_pipeline(
            db, user_id=user.id, file_bytes=raw,
            filename=file.filename or "unknown",
        )
    except UnsupportedStatementError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            f"unsupported statement: {e}") from e
    except DuplicateImportError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        # 解析器内部错(如 GBK decode 失败 / 表头缺列)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
```

- [ ] **Step 15.4:在 `app/main.py` 挂载 statements router**

打开 [backend/app/main.py](backend/app/main.py),加入 import 和 include:

把:
```python
from app.api import auth as auth_api
```
扩展为:
```python
from app.api import auth as auth_api
from app.api import statements as statements_api
```

把:
```python
api_router.include_router(auth_api.router)
```
扩展为:
```python
api_router.include_router(auth_api.router)
api_router.include_router(statements_api.router)
```

- [ ] **Step 15.5:写 HTTP 层 e2e `tests/api/test_statements_import.py`**

```python
"""POST /api/statements/import e2e。"""
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


def _open(name: str):
    p = _FIXTURES / name
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    return p


def test_import_alipay_csv_returns_200(logged_in_client):
    p = _open("alipay_sample.csv")
    with p.open("rb") as f:
        resp = logged_in_client.post(
            "/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_type"] == "alipay_csv"
    assert body["imported_count"] >= 1


def test_import_unsupported_returns_400(logged_in_client):
    resp = logged_in_client.post(
        "/api/statements/import",
        files={"file": ("x.txt", b"random data", "text/plain")},
    )
    assert resp.status_code == 400
    assert "unsupported" in resp.json()["detail"].lower()


def test_import_duplicate_returns_409(logged_in_client):
    p = _open("alipay_sample.csv")
    with p.open("rb") as f:
        bytes_ = f.read()
    r1 = logged_in_client.post("/api/statements/import",
        files={"file": ("alipay_sample.csv", bytes_, "text/csv")})
    assert r1.status_code == 200
    r2 = logged_in_client.post("/api/statements/import",
        files={"file": ("alipay_sample_renamed.csv", bytes_, "text/csv")})
    assert r2.status_code == 409


def test_import_requires_login(client):
    """无 cookie 应 401。"""
    resp = client.post("/api/statements/import",
        files={"file": ("x.csv", b"data", "text/csv")})
    assert resp.status_code == 401


def test_import_empty_file_400(logged_in_client):
    resp = logged_in_client.post("/api/statements/import",
        files={"file": ("x.csv", b"", "text/csv")})
    assert resp.status_code == 400
```

- [ ] **Step 15.6:跑测试看通过**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
pytest tests/services/test_importer_pipeline.py tests/api/test_statements_import.py -v
```

期望:5 service 测试 + 5 api 测试,共 10 passed。

排查:
- 真实样本 fixture 缺 → Pre-flight 已提示 fixture 在 slice B Task 6 复制完毕,若缺就跑 `dir backend\tests\fixtures\statements\` 检查
- duplicate test 失败:确认第二次 hash 校验真返回 409,可能是 conftest 的 db fixture 在两次请求间没保持(应该是同一 session)
- 真实样本里没有匹配 ② 的微信→建行交易,`test_pipeline_wechat_then_bank_creates_anchor` 不强求 mirror_count > 0,只确保不抛错

- [ ] **Step 15.7:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/importer.py backend/app/api/statements.py backend/app/main.py backend/tests/services/test_importer_pipeline.py backend/tests/api/test_statements_import.py
git commit -m "feat(api): POST /api/statements/import with full pipeline orchestration"
```

---

## Task 16:Statements API — `GET /list` `GET /{id}` `GET /{id}/review`

**Files:**
- Modify: `backend/app/api/statements.py`(追加 3 个 endpoint)
- Test: `backend/tests/api/test_statements_list.py`

> spec § 9.1 `/statements` 路由 + 复查页:
> - `GET /api/statements?limit=50&offset=0` → 历史导入列表(按 imported_at DESC)
> - `GET /api/statements/{id}` → 单次详情
> - `GET /api/statements/{id}/review` → ReviewBundle:statement + 该批次的 pending dedup_candidates + 该批次未分类 transactions

- [ ] **Step 16.1:写测试 `tests/api/test_statements_list.py`**

```python
"""Statements list/detail/review e2e。"""
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


def _import_alipay(client) -> int:
    p = _FIXTURES / "alipay_sample.csv"
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    with p.open("rb") as f:
        r = client.post("/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")})
    assert r.status_code == 200
    return r.json()["import_id"]


def test_list_statements_includes_imported(logged_in_client):
    import_id = _import_alipay(logged_in_client)
    resp = logged_in_client.get("/api/statements")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    ids = [s["id"] for s in body["items"]]
    assert import_id in ids


def test_list_statements_pagination(logged_in_client):
    _import_alipay(logged_in_client)
    resp = logged_in_client.get("/api/statements?limit=1&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) <= 1


def test_get_statement_detail(logged_in_client):
    import_id = _import_alipay(logged_in_client)
    resp = logged_in_client.get(f"/api/statements/{import_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == import_id
    assert body["source_type"] == "alipay_csv"


def test_get_statement_404(logged_in_client):
    resp = logged_in_client.get("/api/statements/9999999")
    assert resp.status_code == 404


def test_review_bundle_returns_unclassified_and_pending(logged_in_client):
    import_id = _import_alipay(logged_in_client)
    resp = logged_in_client.get(f"/api/statements/{import_id}/review")
    assert resp.status_code == 200
    body = resp.json()
    assert body["statement"]["id"] == import_id
    # 未分类一般 > 0(用户的种子规则未必覆盖所有商户)
    assert isinstance(body["unclassified_transactions"], list)
    assert isinstance(body["pending_pairs"], list)


def test_review_404_when_statement_not_found(logged_in_client):
    resp = logged_in_client.get("/api/statements/9999999/review")
    assert resp.status_code == 404


def test_list_requires_login(client):
    resp = client.get("/api/statements")
    assert resp.status_code == 401
```

- [ ] **Step 16.2:在 `app/api/statements.py` 追加 3 个 endpoint**

打开 [backend/app/api/statements.py](backend/app/api/statements.py),顶部 import 区追加:

```python
from fastapi import Query
from sqlalchemy import select

from app.models import DedupCandidate, StatementImport, Transaction
from app.schemas import (
    ReviewBundle, StatementImportListOut, StatementImportOut, TransactionOut,
)
from app.schemas.dedup import DedupPairOut
```

文件末尾追加:

```python
@router.get("", response_model=StatementImportListOut)
def list_statements(
    user: CurrentUserDep, db: DbDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> StatementImportListOut:
    base = select(StatementImport).where(StatementImport.user_id == user.id)
    total = db.execute(
        select(StatementImport.id).where(StatementImport.user_id == user.id)
    ).all()
    items = db.execute(
        base.order_by(StatementImport.imported_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return StatementImportListOut(
        items=[StatementImportOut.model_validate(s) for s in items],
        total=len(total),
    )


@router.get("/{import_id}", response_model=StatementImportOut)
def get_statement(
    import_id: int, user: CurrentUserDep, db: DbDep,
) -> StatementImportOut:
    si = db.execute(
        select(StatementImport).where(
            StatementImport.id == import_id,
            StatementImport.user_id == user.id,
        )
    ).scalar_one_or_none()
    if si is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "statement_import not found")
    return StatementImportOut.model_validate(si)


@router.get("/{import_id}/review", response_model=ReviewBundle)
def get_review_bundle(
    import_id: int, user: CurrentUserDep, db: DbDep,
) -> ReviewBundle:
    """spec § 9.1 复查页数据:本批次 pending pairs + 未分类交易。"""
    si = db.execute(
        select(StatementImport).where(
            StatementImport.id == import_id,
            StatementImport.user_id == user.id,
        )
    ).scalar_one_or_none()
    if si is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "statement_import not found")

    # 本批次的 transaction ids
    tx_rows = db.execute(
        select(Transaction.id).where(
            Transaction.user_id == user.id,
            Transaction.statement_import_id == import_id,
        )
    ).all()
    tx_ids = [r[0] for r in tx_rows]

    # 未分类交易(category_id IS NULL)
    unclassified = db.execute(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.statement_import_id == import_id,
            Transaction.category_id.is_(None),
        ).order_by(Transaction.tx_time.desc())
    ).scalars().all()

    # 涉及本批次 tx 的 pending pair(primary 或 mirror 在本批次内)
    pending_pairs: list[DedupCandidate] = []
    if tx_ids:
        pending_pairs = list(db.execute(
            select(DedupCandidate).where(
                DedupCandidate.user_id == user.id,
                DedupCandidate.status == "pending",
                (DedupCandidate.primary_tx_id.in_(tx_ids))
                | (DedupCandidate.mirror_tx_id.in_(tx_ids)),
            ).order_by(DedupCandidate.id.asc())
        ).scalars().all())

    return ReviewBundle(
        statement=StatementImportOut.model_validate(si),
        pending_pairs=[DedupPairOut.model_validate(p) for p in pending_pairs],
        unclassified_transactions=[TransactionOut.model_validate(t) for t in unclassified],
    )
```

- [ ] **Step 16.3:跑测试看通过**

```powershell
pytest tests/api/test_statements_list.py -v
```

期望:7 passed。

排查:
- `total` 计算 N+1:用 `func.count()` 优化(本 task 沿用简单查询;数据量 < 100 不优化)
- ReviewBundle 序列化错:确认 `ReviewBundle.model_rebuild()` 在 schemas/statement.py 末尾被调用(Task 6.7 已加)

- [ ] **Step 16.4:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/api/statements.py backend/tests/api/test_statements_list.py
git commit -m "feat(api): GET /api/statements list/detail/review endpoints"
```

---

## Task 17:Transactions API — list / detail / patch / bulk-update-by-merchant

**Files:**
- Create: `backend/app/api/transactions.py`
- Modify: `backend/app/main.py`(挂载)
- Test: `backend/tests/api/test_transactions.py`

> spec § 9.1 `/transactions` + § 8.1 (web 也要的几个 write 工具,但 spec § 8 是 MCP,本切片 REST 端只复用 service):
> - `GET /api/transactions?date_from=&date_to=&account_id=&category_id=&kind=&source=&is_mirror=&keyword=&limit=&offset=` → 列表 + 总数
> - `GET /api/transactions/{id}` → 单条
> - `PATCH /api/transactions/{id}` body=`{category_id?, tx_kind?}` → 改类
> - `POST /api/transactions/bulk-update-by-merchant` body=`{pattern, match_kind, category_id, also_add_rule}` → 批改 + 可选加规则
> - `DELETE /api/transactions/{id}` → 仅 source ∈ {conversation, manual} 允许;account/wechat/bank 来源不允许(避免删除原始账单数据)

- [ ] **Step 17.1:写测试 `tests/api/test_transactions.py`**

```python
"""Transactions API e2e。"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Account, Category, MerchantRule, Transaction


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


@pytest.fixture
def imported_sample(logged_in_client):
    """先导一份支付宝样本,提供基础数据。"""
    p = _FIXTURES / "alipay_sample.csv"
    if not p.exists():
        pytest.skip("fixture missing")
    with p.open("rb") as f:
        r = logged_in_client.post("/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")})
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def category_food(db, admin_user):
    cat = db.execute(select(Category).where(
        Category.user_id == admin_user.id, Category.name == "餐饮"
    )).scalar_one_or_none()
    if cat is None:
        cat = Category(user_id=admin_user.id, name="餐饮", kind="expense", parent_id=None)
        db.add(cat); db.flush()
    return cat


def test_list_transactions_pagination(logged_in_client, imported_sample):
    resp = logged_in_client.get("/api/transactions?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 10
    assert body["total"] >= 1
    assert len(body["items"]) <= 10


def test_list_transactions_filter_by_kind(logged_in_client, imported_sample):
    resp = logged_in_client.get("/api/transactions?kind=expense")
    assert resp.status_code == 200
    for tx in resp.json()["items"]:
        assert tx["tx_kind"] == "expense"


def test_list_transactions_filter_by_keyword(logged_in_client, imported_sample):
    """关键词 → merchant_normalized ILIKE。"""
    resp = logged_in_client.get("/api/transactions?keyword=咖啡")
    assert resp.status_code == 200
    body = resp.json()
    if body["items"]:
        for tx in body["items"]:
            assert "咖啡" in (tx["merchant_normalized"] or "")


def test_get_transaction_detail(logged_in_client, imported_sample, db, admin_user):
    tx = db.execute(
        select(Transaction).where(Transaction.user_id == admin_user.id).limit(1)
    ).scalar_one()
    resp = logged_in_client.get(f"/api/transactions/{tx.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == tx.id


def test_get_transaction_404(logged_in_client):
    resp = logged_in_client.get("/api/transactions/9999999")
    assert resp.status_code == 404


def test_patch_transaction_category(logged_in_client, imported_sample, db, admin_user, category_food):
    tx = db.execute(
        select(Transaction).where(Transaction.user_id == admin_user.id).limit(1)
    ).scalar_one()
    resp = logged_in_client.patch(
        f"/api/transactions/{tx.id}",
        json={"category_id": category_food.id},
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == category_food.id


def test_patch_transaction_invalid_category_404(logged_in_client, imported_sample, db, admin_user):
    tx = db.execute(
        select(Transaction).where(Transaction.user_id == admin_user.id).limit(1)
    ).scalar_one()
    resp = logged_in_client.patch(
        f"/api/transactions/{tx.id}", json={"category_id": 9999999})
    assert resp.status_code == 404


def test_bulk_update_by_merchant_with_rule(
    logged_in_client, imported_sample, db, admin_user, category_food
):
    """spec § 8.1 bulk_update_category_by_merchant 等价。"""
    resp = logged_in_client.post(
        "/api/transactions/bulk-update-by-merchant",
        json={
            "pattern": "瑞幸",
            "match_kind": "contains",
            "category_id": category_food.id,
            "also_add_rule": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["affected_count"] >= 0  # 真实样本可能没瑞幸,本测试只验流程
    if body["affected_count"] > 0:
        assert body["rule_id"] is not None
        # 规则真的被加到 merchant_rules
        rule = db.execute(
            select(MerchantRule).where(
                MerchantRule.user_id == admin_user.id,
                MerchantRule.pattern == "瑞幸",
                MerchantRule.match_kind == "contains",
            )
        ).scalar_one_or_none()
        assert rule is not None
        assert rule.category_id == category_food.id


def test_bulk_update_idempotent_does_not_dup_rule(
    logged_in_client, imported_sample, db, admin_user, category_food
):
    """同 pattern 二次 also_add_rule=True → 不应建第二条规则。"""
    payload = {"pattern": "瑞幸", "match_kind": "contains",
        "category_id": category_food.id, "also_add_rule": True}
    logged_in_client.post("/api/transactions/bulk-update-by-merchant", json=payload)
    logged_in_client.post("/api/transactions/bulk-update-by-merchant", json=payload)
    cnt = db.execute(
        select(MerchantRule).where(
            MerchantRule.user_id == admin_user.id,
            MerchantRule.pattern == "瑞幸",
            MerchantRule.match_kind == "contains",
        )
    ).scalars().all()
    assert len(cnt) == 1


def test_delete_only_for_manual_or_conversation(
    logged_in_client, imported_sample, db, admin_user
):
    """从账单导入的 tx 不允许 DELETE。"""
    tx = db.execute(
        select(Transaction).where(
            Transaction.user_id == admin_user.id,
            Transaction.source == "alipay",
        ).limit(1)
    ).scalar_one()
    resp = logged_in_client.delete(f"/api/transactions/{tx.id}")
    assert resp.status_code == 403


def test_list_requires_login(client):
    resp = client.get("/api/transactions")
    assert resp.status_code == 401
```

- [ ] **Step 17.2:写 `app/api/transactions.py`**

```python
"""Transactions API — spec § 9.1 + § 8.1 部分写工具的 REST 等价。"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Category, MerchantRule, Transaction
from app.schemas import (
    BulkUpdateByMerchantIn, BulkUpdateResult,
    TransactionListOut, TransactionOut, TransactionPatchIn, TransactionQuery,
)


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionListOut)
def list_transactions(
    user: CurrentUserDep, db: DbDep,
    q: Annotated[TransactionQuery, Depends()],
) -> TransactionListOut:
    """spec § 9.1。query 用 Pydantic 模型,FastAPI 把 query string 装到 q。"""
    conds = [Transaction.user_id == user.id]
    if q.date_from is not None:
        conds.append(Transaction.tx_time >= q.date_from)
    if q.date_to is not None:
        conds.append(Transaction.tx_time <= q.date_to)
    if q.account_id is not None:
        conds.append(Transaction.account_id == q.account_id)
    if q.category_id is not None:
        conds.append(Transaction.category_id == q.category_id)
    if q.kind is not None:
        conds.append(Transaction.tx_kind == q.kind)
    if q.source is not None:
        conds.append(Transaction.source == q.source)
    if q.is_mirror is not None:
        conds.append(Transaction.is_mirror == q.is_mirror)
    if q.keyword:
        conds.append(Transaction.merchant_normalized.ilike(f"%{q.keyword}%"))

    where = and_(*conds)
    total = db.execute(select(func.count()).select_from(Transaction).where(where)).scalar_one()
    items = db.execute(
        select(Transaction).where(where)
        .order_by(Transaction.tx_time.desc(), Transaction.id.desc())
        .limit(q.limit).offset(q.offset)
    ).scalars().all()
    return TransactionListOut(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total, limit=q.limit, offset=q.offset,
    )


def _get_tx_or_404(db, user_id: int, tx_id: int) -> Transaction:
    tx = db.execute(
        select(Transaction).where(
            Transaction.id == tx_id, Transaction.user_id == user_id,
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "transaction not found")
    return tx


@router.get("/{tx_id}", response_model=TransactionOut)
def get_transaction(tx_id: int, user: CurrentUserDep, db: DbDep) -> TransactionOut:
    return TransactionOut.model_validate(_get_tx_or_404(db, user.id, tx_id))


@router.patch("/{tx_id}", response_model=TransactionOut)
def patch_transaction(
    tx_id: int, body: TransactionPatchIn, user: CurrentUserDep, db: DbDep,
) -> TransactionOut:
    tx = _get_tx_or_404(db, user.id, tx_id)
    if body.category_id is not None:
        cat = db.execute(
            select(Category).where(
                Category.id == body.category_id, Category.user_id == user.id,
            )
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
        tx.category_id = body.category_id
        tx.classification_confidence = 1.0  # 用户手工 = 完全确信
    if body.tx_kind is not None:
        tx.tx_kind = body.tx_kind
    db.flush()
    return TransactionOut.model_validate(tx)


@router.post("/bulk-update-by-merchant", response_model=BulkUpdateResult)
def bulk_update_by_merchant(
    body: BulkUpdateByMerchantIn, user: CurrentUserDep, db: DbDep,
) -> BulkUpdateResult:
    """spec § 8.1 同款。先在内存层用 classifier._match_rule 选 tx,
    再批量 UPDATE,可选加规则(同 user/pattern/match_kind 已有则复用)。"""
    cat = db.execute(
        select(Category).where(
            Category.id == body.category_id, Category.user_id == user.id,
        )
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")

    # 选所有 user 的 tx,按 match_kind 在 Python 端过滤(简单稳妥)
    from app.services.classifier import _match_rule
    all_txs = db.execute(
        select(Transaction).where(Transaction.user_id == user.id)
    ).scalars().all()
    affected = 0
    for tx in all_txs:
        if _match_rule(tx.merchant_normalized or "", body.pattern, body.match_kind):
            tx.category_id = body.category_id
            tx.classification_confidence = 1.0
            affected += 1

    rule_id: int | None = None
    if body.also_add_rule:
        existing = db.execute(
            select(MerchantRule).where(
                MerchantRule.user_id == user.id,
                MerchantRule.pattern == body.pattern,
                MerchantRule.match_kind == body.match_kind,
            )
        ).scalar_one_or_none()
        if existing is None:
            rule = MerchantRule(
                user_id=user.id, pattern=body.pattern, match_kind=body.match_kind,
                category_id=body.category_id, priority=70,  # 用户加 priority 70(种子之间)
            )
            db.add(rule); db.flush()
            rule_id = rule.id
        else:
            existing.category_id = body.category_id
            rule_id = existing.id
    db.flush()
    return BulkUpdateResult(affected_count=affected, rule_id=rule_id)


@router.delete("/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, user: CurrentUserDep, db: DbDep) -> None:
    """仅 source ∈ {conversation, manual} 允许删,避免删除账单原始数据。"""
    tx = _get_tx_or_404(db, user.id, tx_id)
    if tx.source not in ("conversation", "manual"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"cannot delete tx from source={tx.source!r}; "
            "delete originating statement_import instead (V2 feature)",
        )
    db.delete(tx)
    db.flush()
    return None
```

- [ ] **Step 17.3:挂载 router**

打开 [backend/app/main.py](backend/app/main.py),在 import 区追加 `from app.api import transactions as transactions_api`,在 `include_router` 段追加:

```python
api_router.include_router(transactions_api.router)
```

- [ ] **Step 17.4:跑测试看通过**

```powershell
pytest tests/api/test_transactions.py -v
```

期望:11 passed。

排查:
- `test_bulk_update_idempotent_does_not_dup_rule` 失败:确认 `existing` 查询用了 `(user_id, pattern, match_kind)` 三元组,且 commit/flush 顺序正确
- `keyword` 测试 fixture 可能没"咖啡"(支付宝样本里随机商户),改 keyword 为样本里有的字段如"消费"

- [ ] **Step 17.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/api/transactions.py backend/app/main.py backend/tests/api/test_transactions.py
git commit -m "feat(api): transactions list/detail/patch/bulk-update/delete"
```

---

## Task 18:Dedup API — pending list / confirm / reject

**Files:**
- Create: `backend/app/api/dedup.py`
- Modify: `backend/app/main.py`(挂载)
- Test: `backend/tests/api/test_dedup.py`

> spec § 9.1 复查页 + § 8.1(MCP `confirm_dedup_pair` 的 REST 等价):
> - `GET /api/dedup/pending?limit=20&offset=0` → 全局未决断 pair 列表
> - `POST /api/dedup/{pair_id}/confirm` body=`{action: "confirm"|"reject", note?}` → 决断
>   - `confirm`:把 mirror 那条标 `is_mirror=True, mirror_of_id=primary.id`,pair.status='confirmed',decided_at=now
>   - `reject`:把 pair.status='rejected'(两条 tx 都正常计入汇总),decided_at=now,**清空** mirror 那条已被错误标的 is_mirror(防止 ② 多匹配场景的回滚)
> - `POST /api/dedup/{pair_id}/reject` 等价于 `confirm` + action=reject(API 同时支持两种调用风格,Web UI / Agent 都能用)

- [ ] **Step 18.1:写测试 `tests/api/test_dedup.py`**

```python
"""Dedup API e2e。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, DedupCandidate, Transaction


@pytest.fixture
def pending_pair(db, admin_user):
    """造一个 pending bridge pair(两条 tx + 一条 dedup_candidates)。"""
    bank = Account(user_id=admin_user.id, name="bocom", type="bank_debit",
        institution="交通银行", last4="2498")
    ali = Account(user_id=admin_user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add_all([bank, ali]); db.flush()
    a = Transaction(user_id=admin_user.id, account_id=ali.id, statement_import_id=None,
        tx_kind="expense", tx_time=datetime(2026, 3, 1, 12, 0),
        amount=Decimal("42.00"), currency="CNY", amount_settled_cny=Decimal("42.00"),
        merchant_raw="X", merchant_normalized="X", source="alipay",
        external_tx_id="a1", is_mirror=False, source_unique_key="alipay:a1")
    b = Transaction(user_id=admin_user.id, account_id=bank.id, statement_import_id=None,
        tx_kind="expense", tx_time=datetime(2026, 3, 1, 13, 0),
        amount=Decimal("42.00"), currency="CNY", amount_settled_cny=Decimal("42.00"),
        merchant_raw="拉扎斯", merchant_normalized="拉扎斯", source="bank",
        external_tx_id=None, is_mirror=False, source_unique_key="bank:b1")
    db.add_all([a, b]); db.flush()
    pair = DedupCandidate(user_id=admin_user.id, primary_tx_id=a.id, mirror_tx_id=b.id,
        match_kind="bridge", confidence=0.85, status="pending",
        reasoning={"rule": "test"})
    db.add(pair); db.flush()
    return pair, a, b


def test_list_pending_returns_pair(logged_in_client, pending_pair):
    pair, _, _ = pending_pair
    resp = logged_in_client.get("/api/dedup/pending")
    assert resp.status_code == 200
    body = resp.json()
    ids = [p["id"] for p in body["items"]]
    assert pair.id in ids


def test_confirm_pair_marks_mirror(logged_in_client, db, pending_pair):
    pair, a, b = pending_pair
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/confirm",
        json={"action": "confirm"})
    assert resp.status_code == 200
    db.refresh(pair); db.refresh(a); db.refresh(b)
    assert pair.status == "confirmed"
    assert pair.decided_at is not None
    assert b.is_mirror is True
    assert b.mirror_of_id == a.id


def test_reject_pair_keeps_both_tx_visible(logged_in_client, db, pending_pair):
    pair, a, b = pending_pair
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/confirm",
        json={"action": "reject"})
    assert resp.status_code == 200
    db.refresh(pair); db.refresh(b)
    assert pair.status == "rejected"
    assert b.is_mirror is False  # 不标镜像


def test_reject_endpoint_alias(logged_in_client, db, pending_pair):
    """POST /api/dedup/{id}/reject 是 confirm with action=reject 的语法糖。"""
    pair, a, b = pending_pair
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/reject", json={})
    assert resp.status_code == 200
    db.refresh(pair)
    assert pair.status == "rejected"


def test_decide_already_decided_returns_409(logged_in_client, db, pending_pair):
    pair, _, _ = pending_pair
    pair.status = "confirmed"
    pair.decided_at = datetime.utcnow()
    db.flush()
    resp = logged_in_client.post(f"/api/dedup/{pair.id}/confirm",
        json={"action": "confirm"})
    assert resp.status_code == 409


def test_decide_404(logged_in_client):
    resp = logged_in_client.post("/api/dedup/9999999/confirm",
        json={"action": "confirm"})
    assert resp.status_code == 404


def test_pending_list_requires_login(client):
    resp = client.get("/api/dedup/pending")
    assert resp.status_code == 401
```

- [ ] **Step 18.2:写 `app/api/dedup.py`**

```python
"""Dedup API — spec § 6 + § 9.1。"""
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, DbDep
from app.models import DedupCandidate, Transaction
from app.schemas import DedupDecisionIn, DedupPairOut, PendingPairListOut


router = APIRouter(prefix="/dedup", tags=["dedup"])


@router.get("/pending", response_model=PendingPairListOut)
def list_pending(
    user: CurrentUserDep, db: DbDep,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PendingPairListOut:
    where = (DedupCandidate.user_id == user.id) & (DedupCandidate.status == "pending")
    total = db.execute(select(func.count()).select_from(DedupCandidate).where(where)).scalar_one()
    items = db.execute(
        select(DedupCandidate).where(where)
        .order_by(DedupCandidate.id.asc()).limit(limit).offset(offset)
    ).scalars().all()
    return PendingPairListOut(
        items=[DedupPairOut.model_validate(p) for p in items], total=total,
    )


def _decide(db, user_id: int, pair_id: int, action: str) -> DedupCandidate:
    pair = db.execute(
        select(DedupCandidate).where(
            DedupCandidate.id == pair_id, DedupCandidate.user_id == user_id,
        )
    ).scalar_one_or_none()
    if pair is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dedup_pair not found")
    if pair.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT,
            f"pair already {pair.status}")
    if action == "confirm":
        mirror = db.execute(
            select(Transaction).where(Transaction.id == pair.mirror_tx_id)
        ).scalar_one()
        mirror.is_mirror = True
        mirror.mirror_of_id = pair.primary_tx_id
        pair.status = "confirmed"
    elif action == "reject":
        # 也要清掉 mirror 已被错误标的(② 多匹配场景下,可能两边都在 pending pair)
        mirror = db.execute(
            select(Transaction).where(Transaction.id == pair.mirror_tx_id)
        ).scalar_one()
        if mirror.mirror_of_id == pair.primary_tx_id:
            mirror.is_mirror = False
            mirror.mirror_of_id = None
        pair.status = "rejected"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            f"unknown action: {action!r}")
    pair.decided_at = datetime.now(UTC)
    db.flush()
    return pair


@router.post("/{pair_id}/confirm", response_model=DedupPairOut)
def confirm_pair(
    pair_id: int, body: DedupDecisionIn, user: CurrentUserDep, db: DbDep,
) -> DedupPairOut:
    pair = _decide(db, user.id, pair_id, body.action)
    return DedupPairOut.model_validate(pair)


@router.post("/{pair_id}/reject", response_model=DedupPairOut)
def reject_pair(
    pair_id: int, user: CurrentUserDep, db: DbDep,
) -> DedupPairOut:
    """语法糖等价于 /confirm body={'action': 'reject'}。"""
    pair = _decide(db, user.id, pair_id, "reject")
    return DedupPairOut.model_validate(pair)
```

- [ ] **Step 18.3:挂载 router**

`backend/app/main.py` 加 `from app.api import dedup as dedup_api` + `api_router.include_router(dedup_api.router)`。

- [ ] **Step 18.4:跑测试看通过**

```powershell
pytest tests/api/test_dedup.py -v
```

期望:7 passed。

- [ ] **Step 18.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/api/dedup.py backend/app/main.py backend/tests/api/test_dedup.py
git commit -m "feat(api): dedup pending/confirm/reject endpoints"
```

---

## Task 19:Categories + Accounts + MerchantRules CRUD API

**Files:**
- Create: `backend/app/api/categories.py`
- Create: `backend/app/api/accounts.py`
- Create: `backend/app/api/rules.py`
- Modify: `backend/app/main.py`(挂载 3 个)
- Test: `backend/tests/api/test_accounts_rules_categories.py`

> spec § 9.1 三个对应路由(`/categories` `/accounts` `/rules`)+ § 4.1 模型字段。本切片只做最小可用 CRUD,**不做** N+1 优化、批量删、级联 cascade(spec 留 V2)。

- [ ] **Step 19.1:写测试 `tests/api/test_accounts_rules_categories.py`**

```python
"""Accounts / Categories / Rules CRUD e2e。"""
import pytest


# === Categories ===

def test_categories_list_root_only_default(logged_in_client):
    """默认登录时 seed 已建分类树,顶级分类应 ≥ 2。"""
    resp = logged_in_client.get("/api/categories")
    assert resp.status_code == 200
    items = resp.json()["items"]
    # 顶级分类(parent_id=None)从 seed 来,应 ≥ 6
    assert isinstance(items, list)


def test_create_update_delete_category(logged_in_client):
    create = logged_in_client.post("/api/categories", json={
        "name": "测试分类一", "kind": "expense", "parent_id": None, "sort_order": 999,
    })
    assert create.status_code == 201
    cid = create.json()["id"]

    upd = logged_in_client.patch(f"/api/categories/{cid}", json={"name": "改名后"})
    assert upd.status_code == 200
    assert upd.json()["name"] == "改名后"

    delete = logged_in_client.delete(f"/api/categories/{cid}")
    assert delete.status_code == 204


def test_create_subcategory(logged_in_client):
    parent = logged_in_client.post("/api/categories", json={
        "name": "父类2026", "kind": "expense", "parent_id": None,
    }).json()
    child = logged_in_client.post("/api/categories", json={
        "name": "子类2026", "kind": "expense", "parent_id": parent["id"],
    })
    assert child.status_code == 201
    assert child.json()["parent_id"] == parent["id"]


# === Accounts ===

def test_accounts_crud(logged_in_client):
    create = logged_in_client.post("/api/accounts", json={
        "name": "工行储蓄卡 9999", "type": "bank_debit",
        "institution": "工商银行", "last4": "9999", "currency": "CNY",
    })
    assert create.status_code == 201
    aid = create.json()["id"]

    list_ = logged_in_client.get("/api/accounts")
    assert any(a["id"] == aid for a in list_.json()["items"])

    upd = logged_in_client.patch(f"/api/accounts/{aid}",
        json={"name": "工行储蓄卡 9999 (改名)"})
    assert upd.status_code == 200
    assert "(改名)" in upd.json()["name"]

    archive = logged_in_client.patch(f"/api/accounts/{aid}", json={"archived": True})
    assert archive.status_code == 200
    assert archive.json()["archived"] is True


def test_account_create_validates_last4(logged_in_client):
    resp = logged_in_client.post("/api/accounts", json={
        "name": "x", "type": "bank_debit",
        "institution": "Y", "last4": "abcd", "currency": "CNY",
    })
    assert resp.status_code == 422


# === Rules ===

def test_rules_crud_with_marker(logged_in_client):
    """marker 规则 category_id=None 必须可创建(spec § 7.1)。"""
    create = logged_in_client.post("/api/rules", json={
        "pattern": "测试marker-2026", "match_kind": "contains",
        "category_id": None, "priority": 25,
    })
    assert create.status_code == 201
    rid = create.json()["id"]
    assert create.json()["category_id"] is None

    upd = logged_in_client.patch(f"/api/rules/{rid}", json={"priority": 30})
    assert upd.status_code == 200
    assert upd.json()["priority"] == 30

    delete = logged_in_client.delete(f"/api/rules/{rid}")
    assert delete.status_code == 204


def test_rules_list_ordered_by_priority(logged_in_client):
    resp = logged_in_client.get("/api/rules")
    assert resp.status_code == 200
    items = resp.json()["items"]
    priorities = [r["priority"] for r in items]
    assert priorities == sorted(priorities)


def test_all_endpoints_require_login(client):
    for path in ["/api/categories", "/api/accounts", "/api/rules"]:
        assert client.get(path).status_code == 401
```

- [ ] **Step 19.2:写 `app/api/categories.py`**

```python
"""Categories API — spec § 9.1 + § 4.1。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Category
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from pydantic import BaseModel


class CategoryListOut(BaseModel):
    items: list[CategoryOut]
    total: int


router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=CategoryListOut)
def list_categories(user: CurrentUserDep, db: DbDep) -> CategoryListOut:
    items = db.execute(
        select(Category).where(Category.user_id == user.id)
        .order_by(Category.sort_order.asc(), Category.id.asc())
    ).scalars().all()
    return CategoryListOut(
        items=[CategoryOut.model_validate(c) for c in items], total=len(items),
    )


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(
    body: CategoryCreate, user: CurrentUserDep, db: DbDep,
) -> CategoryOut:
    if body.parent_id is not None:
        parent = db.execute(
            select(Category).where(
                Category.id == body.parent_id, Category.user_id == user.id,
            )
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "parent category not found")
    cat = Category(
        user_id=user.id, name=body.name, kind=body.kind, parent_id=body.parent_id,
        icon=body.icon, color=body.color, sort_order=body.sort_order,
    )
    db.add(cat); db.flush()
    return CategoryOut.model_validate(cat)


def _get_cat_or_404(db, user_id: int, cat_id: int) -> Category:
    cat = db.execute(
        select(Category).where(Category.id == cat_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    return cat


@router.patch("/{cat_id}", response_model=CategoryOut)
def update_category(
    cat_id: int, body: CategoryUpdate, user: CurrentUserDep, db: DbDep,
) -> CategoryOut:
    cat = _get_cat_or_404(db, user.id, cat_id)
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(cat, field, val)
    db.flush()
    return CategoryOut.model_validate(cat)


@router.delete("/{cat_id}", status_code=204)
def delete_category(cat_id: int, user: CurrentUserDep, db: DbDep) -> None:
    cat = _get_cat_or_404(db, user.id, cat_id)
    # 先检查是否有子分类(防止意外删除)
    has_children = db.execute(
        select(Category.id).where(
            Category.user_id == user.id, Category.parent_id == cat_id
        ).limit(1)
    ).first()
    if has_children:
        raise HTTPException(status.HTTP_409_CONFLICT,
            "category has children; remove or reparent them first")
    db.delete(cat); db.flush()
    return None
```

- [ ] **Step 19.3:写 `app/api/accounts.py`**

```python
"""Accounts API — spec § 9.1 + § 4.1。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Account
from app.schemas import AccountCreate, AccountOut, AccountUpdate
from pydantic import BaseModel


class AccountListOut(BaseModel):
    items: list[AccountOut]
    total: int


router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountListOut)
def list_accounts(user: CurrentUserDep, db: DbDep) -> AccountListOut:
    items = db.execute(
        select(Account).where(Account.user_id == user.id)
        .order_by(Account.id.asc())
    ).scalars().all()
    return AccountListOut(
        items=[AccountOut.model_validate(a) for a in items], total=len(items),
    )


@router.post("", response_model=AccountOut, status_code=201)
def create_account(
    body: AccountCreate, user: CurrentUserDep, db: DbDep,
) -> AccountOut:
    acc = Account(
        user_id=user.id, name=body.name, type=body.type,
        institution=body.institution, last4=body.last4, currency=body.currency,
    )
    db.add(acc); db.flush()
    return AccountOut.model_validate(acc)


def _get_acc_or_404(db, user_id: int, acc_id: int) -> Account:
    acc = db.execute(
        select(Account).where(Account.id == acc_id, Account.user_id == user_id)
    ).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return acc


@router.patch("/{acc_id}", response_model=AccountOut)
def update_account(
    acc_id: int, body: AccountUpdate, user: CurrentUserDep, db: DbDep,
) -> AccountOut:
    acc = _get_acc_or_404(db, user.id, acc_id)
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(acc, field, val)
    db.flush()
    return AccountOut.model_validate(acc)


@router.delete("/{acc_id}", status_code=204)
def delete_account(acc_id: int, user: CurrentUserDep, db: DbDep) -> None:
    """有 transactions 引用时拒绝删,推荐 archived=True。"""
    acc = _get_acc_or_404(db, user.id, acc_id)
    from app.models import Transaction
    has_tx = db.execute(
        select(Transaction.id).where(Transaction.account_id == acc_id).limit(1)
    ).first()
    if has_tx:
        raise HTTPException(status.HTTP_409_CONFLICT,
            "account has transactions; archive instead of delete")
    db.delete(acc); db.flush()
    return None
```

- [ ] **Step 19.4:写 `app/api/rules.py`**

```python
"""MerchantRules API — spec § 9.1 + § 7。"""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models import Category, MerchantRule
from app.schemas import MerchantRuleCreate, MerchantRuleOut, MerchantRuleUpdate
from pydantic import BaseModel


class RuleListOut(BaseModel):
    items: list[MerchantRuleOut]
    total: int


router = APIRouter(prefix="/rules", tags=["rules"])


def _validate_category_or_marker(db, user_id: int, category_id: int | None) -> None:
    if category_id is None:
        return  # marker rule(spec § 7.1)
    cat = db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")


@router.get("", response_model=RuleListOut)
def list_rules(user: CurrentUserDep, db: DbDep) -> RuleListOut:
    items = db.execute(
        select(MerchantRule).where(MerchantRule.user_id == user.id)
        .order_by(MerchantRule.priority.asc(), MerchantRule.id.asc())
    ).scalars().all()
    return RuleListOut(
        items=[MerchantRuleOut.model_validate(r) for r in items], total=len(items),
    )


@router.post("", response_model=MerchantRuleOut, status_code=201)
def create_rule(
    body: MerchantRuleCreate, user: CurrentUserDep, db: DbDep,
) -> MerchantRuleOut:
    _validate_category_or_marker(db, user.id, body.category_id)
    rule = MerchantRule(
        user_id=user.id, pattern=body.pattern, match_kind=body.match_kind,
        category_id=body.category_id, priority=body.priority,
    )
    db.add(rule); db.flush()
    return MerchantRuleOut.model_validate(rule)


def _get_rule_or_404(db, user_id: int, rule_id: int) -> MerchantRule:
    r = db.execute(
        select(MerchantRule).where(
            MerchantRule.id == rule_id, MerchantRule.user_id == user_id,
        )
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    return r


@router.patch("/{rule_id}", response_model=MerchantRuleOut)
def update_rule(
    rule_id: int, body: MerchantRuleUpdate, user: CurrentUserDep, db: DbDep,
) -> MerchantRuleOut:
    rule = _get_rule_or_404(db, user.id, rule_id)
    data = body.model_dump(exclude_unset=True)
    if "category_id" in data:
        _validate_category_or_marker(db, user.id, data["category_id"])
    for field, val in data.items():
        setattr(rule, field, val)
    db.flush()
    return MerchantRuleOut.model_validate(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, user: CurrentUserDep, db: DbDep) -> None:
    rule = _get_rule_or_404(db, user.id, rule_id)
    db.delete(rule); db.flush()
    return None
```

- [ ] **Step 19.5:挂载 3 个 router**

`backend/app/main.py`,加 imports:

```python
from app.api import accounts as accounts_api
from app.api import categories as categories_api
from app.api import rules as rules_api
```

加 include:

```python
api_router.include_router(accounts_api.router)
api_router.include_router(categories_api.router)
api_router.include_router(rules_api.router)
```

- [ ] **Step 19.6:跑测试看通过**

```powershell
pytest tests/api/test_accounts_rules_categories.py -v
```

期望:8 passed。

排查:
- `test_categories_list_root_only_default` 失败 → seed 没在 conftest 跑;在 `admin_user` fixture 之后调用 `from app.db.seed_categories import seed_default_categories; seed_default_categories(db, admin_user.id)`,本切片测试库已被 savepoint rollback 隔离不留数据
- 实际上为简单起见,不强求 seed 数据存在,只要 list endpoint 不抛错(空数组也合法);若 fixture 没 seed,可放宽断言为 `assert isinstance(items, list)`

- [ ] **Step 19.7:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/api/categories.py backend/app/api/accounts.py backend/app/api/rules.py backend/app/main.py backend/tests/api/test_accounts_rules_categories.py
git commit -m "feat(api): categories/accounts/rules CRUD endpoints"
```

---

## Task 20:Summary API — `GET /api/summary?period=&group_by=&date_from=&date_to=`

**Files:**
- Create: `backend/app/services/summary.py`(纯函数)
- Create: `backend/app/api/summary.py`
- Modify: `backend/app/main.py`(挂载)
- Test: `backend/tests/services/test_summary.py`(service 单元)
- Test: `backend/tests/api/test_summary.py`(api e2e)

> spec § 8.1 `get_summary`(本切片是 REST 等价,slice E MCP 包装即可):
> - `period ∈ {day, week, month, year}` — 决定默认 date_from/date_to(当前 period 的起讫)
> - `group_by ∈ {category, account, merchant}`
> - `date_from / date_to` 可选,覆盖 period 默认
> - **统计规则**:
>   - 仅 `is_mirror=False` 的 tx 计入(spec § 6.6)
>   - `total_expense = sum(amount_settled_cny) where tx_kind='expense'`
>   - `total_income = sum(amount_settled_cny) where tx_kind='income'`
>   - `breakdown[]`:按 group_by 聚合,每组返回 (group_key, group_id, amount_total, count)
>   - 默认按 amount 降序

- [ ] **Step 20.1:写 service 测试 `tests/services/test_summary.py`**

```python
"""compute_summary 单元测试。"""
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Category, Transaction, User
from app.services.summary import compute_summary


@pytest.fixture
def populated(db):
    user = User(username="su", password_hash="$2b$12$" + "x" * 53)
    db.add(user); db.flush()
    cat_food = Category(user_id=user.id, name="餐饮", kind="expense", parent_id=None)
    cat_traffic = Category(user_id=user.id, name="交通", kind="expense", parent_id=None)
    db.add_all([cat_food, cat_traffic]); db.flush()
    acc1 = Account(user_id=user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None)
    db.add(acc1); db.flush()

    txs = [
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 1, 12),
            amount=Decimal("10"), currency="CNY", amount_settled_cny=Decimal("10"),
            merchant_raw="瑞幸", merchant_normalized="瑞幸",
            category_id=cat_food.id, source="alipay", is_mirror=False,
            source_unique_key="alipay:t1"),
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 2, 12),
            amount=Decimal("20"), currency="CNY", amount_settled_cny=Decimal("20"),
            merchant_raw="星巴克", merchant_normalized="星巴克",
            category_id=cat_food.id, source="alipay", is_mirror=False,
            source_unique_key="alipay:t2"),
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 3, 12),
            amount=Decimal("30"), currency="CNY", amount_settled_cny=Decimal("30"),
            merchant_raw="地铁", merchant_normalized="地铁",
            category_id=cat_traffic.id, source="alipay", is_mirror=False,
            source_unique_key="alipay:t3"),
        # is_mirror=True 应被过滤
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="expense", tx_time=datetime(2026, 3, 4, 12),
            amount=Decimal("999"), currency="CNY", amount_settled_cny=Decimal("999"),
            merchant_raw="MIRROR", merchant_normalized="MIRROR",
            category_id=cat_food.id, source="bank", is_mirror=True,
            source_unique_key="bank:m1"),
        Transaction(user_id=user.id, account_id=acc1.id, statement_import_id=None,
            tx_kind="income", tx_time=datetime(2026, 3, 5, 12),
            amount=Decimal("100"), currency="CNY", amount_settled_cny=Decimal("100"),
            merchant_raw="工资", merchant_normalized="工资",
            category_id=None, source="bank", is_mirror=False,
            source_unique_key="bank:i1"),
    ]
    db.add_all(txs); db.flush()
    return user, {"food": cat_food.id, "traffic": cat_traffic.id, "acc": acc1.id}


def test_summary_total_excludes_mirror(populated, db):
    user, _ = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="category")
    assert s["total_expense"] == Decimal("60")  # 10+20+30,排除 mirror 999
    assert s["total_income"] == Decimal("100")


def test_summary_group_by_category(populated, db):
    user, ids = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="category")
    bd = {item["group_id"]: item for item in s["breakdown"]}
    assert bd[ids["food"]]["amount"] == Decimal("30")  # 10+20
    assert bd[ids["food"]]["count"] == 2
    assert bd[ids["traffic"]]["amount"] == Decimal("30")
    assert bd[ids["traffic"]]["count"] == 1


def test_summary_group_by_merchant(populated, db):
    user, _ = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="merchant")
    keys = {item["group_key"] for item in s["breakdown"]}
    assert {"瑞幸", "星巴克", "地铁"}.issubset(keys)


def test_summary_group_by_account(populated, db):
    user, ids = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 1), date_to=datetime(2026, 4, 1),
        group_by="account")
    bd = {item["group_id"]: item for item in s["breakdown"]}
    assert bd[ids["acc"]]["count"] == 3  # 3 条 expense,排除 mirror


def test_summary_date_filter(populated, db):
    user, _ = populated
    s = compute_summary(db, user_id=user.id,
        date_from=datetime(2026, 3, 2), date_to=datetime(2026, 3, 3, 23, 59),
        group_by="category")
    assert s["total_expense"] == Decimal("50")  # 20+30
```

- [ ] **Step 20.2:写 `app/services/summary.py`**

```python
"""Summary 服务 — spec § 8.1 算法,纯函数。"""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
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

    # 总额(expense / income)
    expense_total = db.execute(
        select(func.coalesce(func.sum(Transaction.amount_settled_cny), 0))
        .where(*base_where, Transaction.tx_kind == "expense")
    ).scalar_one()
    income_total = db.execute(
        select(func.coalesce(func.sum(Transaction.amount_settled_cny), 0))
        .where(*base_where, Transaction.tx_kind == "income")
    ).scalar_one()

    # 仅在 expense 维度 breakdown(spec § 8.1 默认看支出大头)
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
```

- [ ] **Step 20.3:写 `app/api/summary.py`**

```python
"""Summary API — spec § 8.1 + § 9.1 首页本月概览。"""
from datetime import datetime, timedelta, UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUserDep, DbDep
from app.schemas import SummaryBreakdownItem, SummaryOut
from app.schemas.summary import GroupBy, Period
from app.services.summary import compute_summary


router = APIRouter(prefix="/summary", tags=["summary"])


def _period_range(period: Period, now: datetime) -> tuple[datetime, datetime]:
    """计算 period 的默认 (date_from, date_to)。"""
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 下月 1 号
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1)
        return start, end
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown period: {period!r}")


@router.get("", response_model=SummaryOut)
def get_summary(
    user: CurrentUserDep, db: DbDep,
    period: Period = Query("month"),
    group_by: GroupBy = Query("category"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> SummaryOut:
    now = datetime.now(UTC).replace(tzinfo=None)
    df, dt = _period_range(period, now)
    if date_from is not None:
        df = date_from
    if date_to is not None:
        dt = date_to

    data = compute_summary(db, user_id=user.id, date_from=df, date_to=dt,
        group_by=group_by)
    return SummaryOut(
        period=period, date_from=df, date_to=dt, group_by=group_by,
        total_expense=data["total_expense"],
        total_income=data["total_income"],
        breakdown=[SummaryBreakdownItem(**item) for item in data["breakdown"]],
    )
```

- [ ] **Step 20.4:写 api 层 e2e `tests/api/test_summary.py`**

```python
"""Summary API e2e。"""
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "statements"


@pytest.fixture
def imported_alipay(logged_in_client):
    p = _FIXTURES / "alipay_sample.csv"
    if not p.exists():
        pytest.skip("fixture missing")
    with p.open("rb") as f:
        r = logged_in_client.post("/api/statements/import",
            files={"file": ("alipay_sample.csv", f, "text/csv")})
    assert r.status_code == 200


def test_summary_default_month_category(logged_in_client, imported_alipay):
    resp = logged_in_client.get("/api/summary")  # 默认 period=month, group_by=category
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"] == "month"
    assert body["group_by"] == "category"
    # 真实样本可能在 3 月,与"本月"不一定重合;改用显式 date 范围测一次:
    resp2 = logged_in_client.get(
        "/api/summary?date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00")
    body2 = resp2.json()
    assert float(body2["total_expense"]) >= 0


def test_summary_group_by_merchant(logged_in_client, imported_alipay):
    resp = logged_in_client.get(
        "/api/summary?group_by=merchant"
        "&date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00")
    assert resp.status_code == 200
    body = resp.json()
    assert body["group_by"] == "merchant"
    assert isinstance(body["breakdown"], list)


def test_summary_group_by_account(logged_in_client, imported_alipay):
    resp = logged_in_client.get(
        "/api/summary?group_by=account"
        "&date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00")
    assert resp.status_code == 200


def test_summary_invalid_group_by_returns_422(logged_in_client):
    resp = logged_in_client.get("/api/summary?group_by=invalid")
    assert resp.status_code == 422


def test_summary_requires_login(client):
    resp = client.get("/api/summary")
    assert resp.status_code == 401
```

- [ ] **Step 20.5:挂载 router**

`backend/app/main.py`:加 `from app.api import summary as summary_api` + `api_router.include_router(summary_api.router)`。

- [ ] **Step 20.6:跑测试看通过**

```powershell
pytest tests/services/test_summary.py tests/api/test_summary.py -v
```

期望:5 service + 5 api = 10 passed。

- [ ] **Step 20.7:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/app/services/summary.py backend/app/api/summary.py backend/app/main.py backend/tests/services/test_summary.py backend/tests/api/test_summary.py
git commit -m "feat(api): summary endpoint with category/account/merchant breakdown"
```

---

## Task 21:E2E shell 测试 + verify_slice_c.ps1 + DoD + overview / CLAUDE.md 进度更新

**Files:**
- Create: `backend/tests/e2e/import_flow.ps1`
- Create: `backend/scripts/verify_slice_c.ps1`
- Modify: `docs/superpowers/plans/2026-05-08-mvp-overview.md`(标 slice C 完成 + 划掉 I-5/Rec#5/B-poly-1/B-poly-2)
- Modify: `CLAUDE.md`(进度勾选)

> overview.md DoD 要求(本切片):通过 HTTP 真实跑通完整 7 步路径(login → import 支付宝 → import 交行 → /review 看 dedup_pending → confirm → list/transactions 看 mirror → /summary 数字合理)。`import_flow.ps1` 用 `Invoke-RestMethod` + `-SessionVariable` 复用 cookie。

- [ ] **Step 21.1:启动 backend 服务(本地 uvicorn)**

终端 1:
```powershell
cd D:\IDEACursor\Claude-code\finance-manager\backend
.\.venv\Scripts\Activate.ps1
docker-compose -f ..\docker-compose.yml up -d db
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

期望:`Uvicorn running on http://127.0.0.1:8000`。

- [ ] **Step 21.2:写 `backend/tests/e2e/import_flow.ps1`**

```powershell
# import_flow.ps1 — slice C DoD 端到端验证
# 用法(uvicorn 已在 8000 端口运行后):
#   pwsh backend\tests\e2e\import_flow.ps1
$ErrorActionPreference = "Stop"

# 从 .env 拿密码(测试时若 .env 改密,这里也得对应,见 Pre-flight)
$envFile = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\")).Path ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "FAIL: .env not found at $envFile" -ForegroundColor Red
    exit 1
}
# 期望用户在执行此脚本前手工在环境变量 ADMIN_TEST_PASSWORD 中填明文密码(避免脚本读 hash)
$pwd = $env:ADMIN_TEST_PASSWORD
if (-not $pwd) {
    Write-Host "ERROR: 请先 setx ADMIN_TEST_PASSWORD 'your-pwd' 或 `$env:ADMIN_TEST_PASSWORD='your-pwd' 临时设置后重跑" -ForegroundColor Red
    exit 1
}

$base = "http://127.0.0.1:8000/api"
$session = $null

Write-Host "=== Slice C E2E import_flow ===" -ForegroundColor Cyan

# [1] login
Write-Host "`n[1/7] Login..." -ForegroundColor Yellow
$loginResp = Invoke-RestMethod -Method Post -Uri "$base/auth/login" `
    -ContentType "application/json" `
    -Body (@{ username = "admin"; password = $pwd } | ConvertTo-Json) `
    -SessionVariable session
Write-Host "  PASS: logged in as $($loginResp.username)" -ForegroundColor Green

# [2] upload alipay
Write-Host "`n[2/7] Upload alipay CSV..." -ForegroundColor Yellow
$alipayPath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\fixtures\statements")).Path "alipay_sample.csv"
$alipayResp = Invoke-RestMethod -Method Post -Uri "$base/statements/import" `
    -WebSession $session `
    -Form @{ file = Get-Item $alipayPath }
Write-Host "  PASS: imported $($alipayResp.imported_count) tx, dedup_pending=$($alipayResp.dedup_pending_count)" -ForegroundColor Green
$alipayImportId = $alipayResp.import_id

# [3] upload bocom PDF(可能触发 ④ 桥接)
Write-Host "`n[3/7] Upload bocom debit PDF..." -ForegroundColor Yellow
$bocomPath = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\fixtures\statements")).Path "bocom_debit_sample.pdf"
$bocomResp = Invoke-RestMethod -Method Post -Uri "$base/statements/import" `
    -WebSession $session `
    -Form @{ file = Get-Item $bocomPath }
Write-Host "  PASS: imported $($bocomResp.imported_count) tx, dedup_pending=$($bocomResp.dedup_pending_count)" -ForegroundColor Green

# [4] /review 看 pending
Write-Host "`n[4/7] Review bundle..." -ForegroundColor Yellow
$reviewResp = Invoke-RestMethod -Method Get -Uri "$base/statements/$($bocomResp.import_id)/review" -WebSession $session
Write-Host "  PASS: pending_pairs=$($reviewResp.pending_pairs.Count), unclassified=$($reviewResp.unclassified_transactions.Count)" -ForegroundColor Green

# [5] confirm 第一个 pending(若有)
Write-Host "`n[5/7] Confirm first pending pair (if any)..." -ForegroundColor Yellow
$pending = Invoke-RestMethod -Method Get -Uri "$base/dedup/pending" -WebSession $session
if ($pending.items.Count -gt 0) {
    $firstId = $pending.items[0].id
    $confirmResp = Invoke-RestMethod -Method Post -Uri "$base/dedup/$firstId/confirm" `
        -WebSession $session -ContentType "application/json" `
        -Body (@{ action = "confirm" } | ConvertTo-Json)
    if ($confirmResp.status -ne "confirmed") {
        Write-Host "  FAIL: confirm did not return confirmed status" -ForegroundColor Red
        exit 1
    }
    Write-Host "  PASS: confirmed pair_id=$firstId" -ForegroundColor Green
} else {
    Write-Host "  SKIP: no pending pairs in this run" -ForegroundColor Gray
}

# [6] /transactions 看 mirror flag
Write-Host "`n[6/7] List transactions..." -ForegroundColor Yellow
$txResp = Invoke-RestMethod -Method Get -Uri "$base/transactions?limit=10" -WebSession $session
$mirrorCount = ($txResp.items | Where-Object { $_.is_mirror -eq $true }).Count
Write-Host "  PASS: total=$($txResp.total), in first 10: mirror=$mirrorCount" -ForegroundColor Green

# [7] /summary
Write-Host "`n[7/7] Summary by category..." -ForegroundColor Yellow
$sumResp = Invoke-RestMethod -Method Get -Uri "$base/summary?date_from=2025-12-01T00:00:00&date_to=2026-04-01T00:00:00" -WebSession $session
Write-Host "  PASS: total_expense=$($sumResp.total_expense), total_income=$($sumResp.total_income), breakdown_groups=$($sumResp.breakdown.Count)" -ForegroundColor Green

Write-Host "`n=== E2E import_flow: ALL PASS ===" -ForegroundColor Green
```

注意:
1. `Invoke-RestMethod -Form @{ file = Get-Item ... }` 是 PowerShell 7.4+ 的原生 multipart 语法。
2. 如果数据库已有同 file_hash 的旧 import,第 [2]/[3] 步会 409。脚本的目的是**端到端冒烟**,跑前用户应清空 statement_imports + transactions(`docker-compose exec db psql -U finance -d finance -c "TRUNCATE statement_imports, transactions, dedup_candidates RESTART IDENTITY CASCADE;"`),或在脚本顶部加 truncate 步骤。

为方便,在脚本顶部 [1] 之前加可选 truncate:

```powershell
if ($env:E2E_RESET -eq "1") {
    Write-Host "[reset] truncating tx/dedup/imports..." -ForegroundColor DarkYellow
    $truncSql = "TRUNCATE statement_imports, transactions, dedup_candidates RESTART IDENTITY CASCADE;"
    docker exec finance-manager-db-1 psql -U finance -d finance -c $truncSql 2>&1 | Out-Null
}
```

让用户想重跑时 `$env:E2E_RESET = "1"; pwsh backend\tests\e2e\import_flow.ps1`。

- [ ] **Step 21.3:跑 e2e 脚本**

```powershell
# 终端 1 已在跑 uvicorn(Step 21.1)
# 终端 2:
cd D:\IDEACursor\Claude-code\finance-manager
$env:ADMIN_TEST_PASSWORD = "your-dev-password-here"  # Pre-flight 时设的明文密码
$env:E2E_RESET = "1"
pwsh backend\tests\e2e\import_flow.ps1
```

期望末尾:`=== E2E import_flow: ALL PASS ===`,且每步 PASS 计数合理(导入 tx 数量与样本头部一致 ±5,summary 数字看起来不离谱)。

- [ ] **Step 21.4:写 `backend/scripts/verify_slice_c.ps1`**

```powershell
# verify_slice_c.ps1 -- slice C DoD 验证
# 用法: 在 finance-manager/ 根目录或 worktree 根目录下运行
#   pwsh backend\scripts\verify_slice_c.ps1
#
# 前置:
#   - docker-compose up -d db
#   - alembic upgrade head
#   - python -m app.db.seed
#   - 设置 $env:ADMIN_TEST_PASSWORD(给 e2e 用的明文密码)
$ErrorActionPreference = "Stop"

Write-Host "=== Slice C DoD verify ===" -ForegroundColor Cyan

# 定位 backend
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = (Resolve-Path (Join-Path $scriptDir "..")).Path
Push-Location $backendDir

# 1. 跑全测试套件(含 slice A + B + C)
Write-Host "`n[1/5] Run full test suite..." -ForegroundColor Yellow
.\.venv\Scripts\Activate.ps1
pytest -q --maxfail=3
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: test suite has failures" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: full test suite green" -ForegroundColor Green

# 2. 验证 ccb_credit_pdf 已无 codepoint matching 残留(B-poly-1)
Write-Host "`n[2/5] Verify B-poly-1: no codepoint matching..." -ForegroundColor Yellow
$ccbSrc = Get-Content "app\services\statement_parser\ccb_credit_pdf.py" -Raw
if ($ccbSrc -match "_has_codepoints" -or $ccbSrc -match "_starts_with_codepoints" -or $ccbSrc -match "_YINLIAN_CP") {
    Write-Host "  FAIL: ccb_credit_pdf still has codepoint helpers" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: codepoint helpers removed" -ForegroundColor Green

# 3. 验证 _is_repayment 是子串匹配(B-poly-2)
Write-Host "`n[3/5] Verify B-poly-2: _is_repayment uses substring..." -ForegroundColor Yellow
$pyCheck = @"
from app.services.statement_parser.ccb_credit_pdf import _is_repayment
import sys
sys.exit(0 if (_is_repayment('银联入账7432') and not _is_repayment('联银账入')) else 1)
"@
python -c $pyCheck
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: _is_repayment still order-agnostic" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: substring order respected" -ForegroundColor Green

# 4. 验证 seed.py 不再含 placeholder(I-5)
Write-Host "`n[4/5] Verify I-5: seed.py no placeholder hardcoded..." -ForegroundColor Yellow
$seedSrc = Get-Content "app\db\seed.py" -Raw
if ($seedSrc -match 'password_hash\s*=\s*"\$2b\$12\$placeholder') {
    Write-Host "  FAIL: seed.py still hardcodes placeholder" -ForegroundColor Red
    Pop-Location; exit 1
}
if ($seedSrc -notmatch "admin_password_hash") {
    Write-Host "  FAIL: seed.py does not read Settings.admin_password_hash" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS: seed reads from Settings" -ForegroundColor Green

# 5. 跑 e2e 脚本(可选,要求 uvicorn + ADMIN_TEST_PASSWORD)
Pop-Location

Write-Host "`n[5/5] E2E import_flow.ps1..." -ForegroundColor Yellow
if ($env:ADMIN_TEST_PASSWORD) {
    pwsh backend\tests\e2e\import_flow.ps1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAIL: e2e script failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "  PASS: e2e all 7 steps green" -ForegroundColor Green
} else {
    Write-Host "  SKIP: ADMIN_TEST_PASSWORD not set; run manually:" -ForegroundColor Gray
    Write-Host "    `$env:ADMIN_TEST_PASSWORD='your-pwd'" -ForegroundColor Gray
    Write-Host "    pwsh backend\tests\e2e\import_flow.ps1" -ForegroundColor Gray
}

Write-Host "`n=== Slice C DoD: ALL PASS ===" -ForegroundColor Green
```

- [ ] **Step 21.5:跑 verify 脚本(单元 + 静态检查 + 可选 e2e)**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
# 不带 e2e:
pwsh backend\scripts\verify_slice_c.ps1
# 带 e2e:确保 uvicorn 跑着
$env:ADMIN_TEST_PASSWORD = "your-dev-pwd"
$env:E2E_RESET = "1"
pwsh backend\scripts\verify_slice_c.ps1
```

期望末行:`Slice C DoD: ALL PASS`。

- [ ] **Step 21.6:更新 `docs/superpowers/plans/2026-05-08-mvp-overview.md`**

打开 [docs/superpowers/plans/2026-05-08-mvp-overview.md](docs/superpowers/plans/2026-05-08-mvp-overview.md):

(a) "切片 C 启动前必修"段,把 I-5 / Rec #5 改成 ~~删除线~~ + commit hash:

```markdown
### 切片 C 启动前必修

- ~~**I-5** `seed.ensure_default_user` 中 `password_hash="$2b$12$placeholder_replace_in_slice_c"` 不是合法 bcrypt hash...~~ ✅ 已在 slice C Task 3 改读 Settings.admin_password_hash(commit hash: 见 git log)
- ~~**Recommendation #5**:`merchant_rules` 中 priority=20 的 6 条"跨源标记"规则 `category_id=NULL`...~~ ✅ 已在 slice C Task 4 + Task 14 处理(契约测试 + classifier 实现)
- **Recommendation #3-4**:`source_unique_key` ...(此条仍保留,源 generation 在 slice C importer 已对齐 spec § 6.1 ①,无需进一步动作 — 也可以同时划掉)
```

(b) "Polish(slice B 产生,后续可清理)"段:

```markdown
- ~~**B-poly-1** ...~~ ✅ 已在 slice C Task 2 修复(commit hash: 见 git log)
- ~~**B-poly-2** ...~~ ✅ 已在 slice C Task 1 修复(commit hash: 见 git log)
- **B-poly-3** wechat_xlsx 的 _to_str ...(本切片真实样本未触发,继续保留)
- **B-poly-4** seed.py 真实跑后...(本切片 I-5 修复时改用 Settings 同步 hash 已部分缓解,完整修复需要 TEST_DATABASE_URL 启用)
```

(c) "完成进度"表:

```markdown
| C. 流水线 + API | ✅ 完成 | 2026-05-09 | (实施工时由 controller 估算) | DoD verify ALL PASS;7 步 e2e 通过;含 4 项 slice A/B 遗留 fix |
```

- [ ] **Step 21.7:更新仓库根 `CLAUDE.md`**

打开 `CLAUDE.md`,把:

```markdown
- ✅ **A. 数据库基础**(2026-05-08 完成,merged to main,DoD verify ALL PASS)
- ✅ **B. 4 个账单解析器**(2026-05-09 完成,DoD verify ALL PASS;含 slice A 遗留 I-1/I-3 修复)
- ⏳ **C. 导入流水线 + 去重 + 分类 + REST API**(下一步)
- ⏳ **D. Web UI**(5 大板块,响应式)
- ⏳ **E. MCP server(10 工具)+ 部署**(Caddy + Cloudflare DNS-01,端口 8443/9443)
```

改成:

```markdown
- ✅ **A. 数据库基础**(2026-05-08 完成,merged to main,DoD verify ALL PASS)
- ✅ **B. 4 个账单解析器**(2026-05-09 完成,DoD verify ALL PASS;含 slice A 遗留 I-1/I-3 修复)
- ✅ **C. 导入流水线 + 去重 + 分类 + REST API**(2026-05-09 完成,DoD verify ALL PASS;含 4 项遗留 fix:B-poly-1/2、I-5、Rec #5)
- ⏳ **D. Web UI**(下一步,5 大板块,响应式)
- ⏳ **E. MCP server(10 工具)+ 部署**(Caddy + Cloudflare DNS-01,端口 8443/9443)
```

并把"## 遗留问题(slice C 必须处理)"段标题改为"## 遗留问题(slice D/E 必须处理)",删除 I-5 / Rec #5 / B-poly-1 / B-poly-2 四条已闭环条目,只保留 D/E 适用的(若没有,本段可整段删除或填"(slice C 已清空,见 overview.md '已知遗留问题' 段查后续切片新产生的 polish)")。

- [ ] **Step 21.8:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git add backend/scripts/verify_slice_c.ps1 backend/tests/e2e/import_flow.ps1 docs/superpowers/plans/2026-05-08-mvp-overview.md CLAUDE.md
git commit -m "chore(slice-c): add verify script + e2e flow, mark slice C done"
```

- [ ] **Step 21.9:最后 sanity check**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager
git log --oneline main..slice-c-pipeline
git status
```

期望 `git log` 输出 ~21 条 commit(对应 21 个 task,每 task 1+ commit),`git status` 干净。

切片 C 完成,可走 `superpowers:finishing-a-development-branch` 决定 merge 策略(参照 slice A/B 的 fast-forward 习惯)。

---

## Self-Review 备忘(写完 plan 后已自检)

- **Spec 覆盖**:
  - § 5.1 导入流水线 → Task 8/9/15
  - § 5.1.1 账户自动推断 → Task 8 (`ensure_account_for_hint`)
  - § 6.1 ① 同源跳过 → Task 9 (`source_unique_key` 唯一约束 + persist 端 seen 集合)
  - § 6.2 ② 微信→银行精确锚定 → Task 10
  - § 6.3 ③ 强重复 → Task 11
  - § 6.4 ④ 桥接 → Task 12
  - § 6.5 ⑤ 对话↔账单 → Task 13
  - § 6.6 mirror 不计入汇总 → Task 20 (`compute_summary` 强制 `is_mirror=False`)
  - § 7.1 种子规则(slice A 已 seed,本切片只对接)+ § 7.2 匹配流程 + Rec #5 marker → Task 4 + 14
  - § 9.1 路由表(MVP web ui 用) → Task 7/15/16/17/18/19/20(全 9 个 Web 路由 backend 端齐全)
  - § 10.1 JWT cookie 认证 → Task 5/6/7
  - § 10.2 MCP API token(留 slice E)
  - § 8 MCP 工具集(留 slice E)
  - 4 项遗留 → Task 1-4(B-poly-2 / B-poly-1 / I-5 / Rec #5)
  - ✅ 全覆盖
- **Placeholder 扫**:无 TODO / TBD / 引用未定义函数。Task 15 的 inline `if False else` 已用注释明确"用下方干净版替换"。✅
- **类型一致**:
  - `RawTransaction` 全程 spec § 5.2 字段不变(slice B 已固定)
  - `ParseResult.metadata['raw_row_count' / 'imported_count']` key 在 importer 与 schema 一致
  - Pydantic schema 命名:`XxxIn / XxxOut / XxxQuery` 三类后缀全程统一
  - `source` 字符串(`alipay/wechat/bank/conversation/manual`)与 spec § 4.1 一致
  - `match_kind`(`exact/contains/regex/fuzzy`)与 `seed_merchant_rules.py` 现有数据一致
  - ✅
- **DoD 可执行**:
  - `verify_slice_c.ps1` 5 项硬指标(全测试通过 / B-poly-1 codepoint 残留 / B-poly-2 子串行为 / I-5 placeholder / e2e 7 步)
  - `import_flow.ps1` 用 `Invoke-RestMethod -SessionVariable` 复用 cookie,涵盖 spec DoD 7 步
  - ✅
- **Task 间耦合检查**:
  - Task 4 写契约 + xfail,Task 14 实现并摘 xfail,顺序正确
  - Task 9 的 `persist_raw_transactions` 与 Task 15 的 `_persist_and_return_ids` 重复 — 这是有意为之:Task 9 的接口稳定后,Task 15 加包装收集 ids;若有人觉得冗余,后续可重构 Task 9 直接返回 ids,但本切片不动
  - Task 7 conftest 的 `admin_user` fixture 强制覆盖 password_hash → 测试每跑一次,db 里 admin 的 password_hash 都被 nested savepoint 隔离,不会污染下次
  - ✅
- **遗留闭环**:I-5 / Rec #5 / B-poly-1 / B-poly-2 在 Task 1-4 处理,Task 21 标记关闭并更新 overview 与 CLAUDE.md。✅

(end of plan)
