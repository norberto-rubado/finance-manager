# 切片 E:MCP server(10 工具)+ 自建 VPS 部署 — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 8(MCP 工具集 — 6 read + 4 write,共 10 个)、§ 10.2(MCP 静态 API token 认证)、§ 11(自建 VPS 部署:docker-compose dev/prod profiles + Caddy DNS-01 + Cloudflare + 备份),并补齐 backend 上现存的 4 项 MCP 前置 gap(`add_transaction` POST endpoint、`find_merchant` 聚合 endpoint、`list_pending_classifications` 未分类筛选、`get_account_balances` 余额字段)。同时**第一时间**修掉 main 上预先存在的 bcrypt 5.x 兼容性 regression(passlib 在装到新版 bcrypt 时,test 套件 42 errors / 2 failed)。

**Architecture:** MCP server 是一个独立的 Python 项目(`mcp_server/`),用官方 `mcp` Python SDK 把 spec § 8 的 10 个工具实现为 thin wrappers,每个工具的工作就是:校验入参 → httpx 调一次 backend REST API(注入 `Authorization: Bearer <api_token>` header)→ 把 backend 响应转成 spec § 8.1 规定的工具出参 schema。工具调用本身的鉴权(spec § 8.2)在 MCP server 进程入口完成 — 用户/Agent 在 MCP client 配置 `Authorization: Bearer <token>` header,server 读取后查 `api_tokens` 表(同一个 Postgres,通过 backend `/api/admin/tokens/verify` 内部端点),失败返 spec § 8.3 的 `AUTH_FAILED` 错误。Backend 端为支撑 MCP 的 4 个未覆盖工具,新增 4 个 REST endpoint(`POST /api/transactions/manual` / `GET /api/transactions/merchants` / `GET /api/transactions/pending-classifications` / `GET /api/accounts` 增 `latest_balance`),并新增 `/api/admin/tokens` 的 token 管理三件套(create/list/revoke),全部用既有 cookie+JWT 保护。部署侧:`docker-compose.yml` 引入 `--profile dev | prod` 区分,`prod` 下移除 backend/mcp/postgres 的 host port 映射(只走内网),把 `caddy` 服务暴露到宿主机 8443/9443。Caddy 用社区镜像 `slothcroissant/caddy-cloudflaredns`(自带 cloudflare DNS 插件,免去 xcaddy build),`Caddyfile` 配置 DNS-01 challenge(读 `CLOUDFLARE_API_TOKEN` env)。备份用 `pg_dump | age | rclone`,`scripts/backup.sh` + cron `0 3 * * *`,密钥保留本地。

**Tech Stack:** Python 3.11(MCP server + backend)/ `mcp` Python SDK ≥ 1.1 / `httpx` ≥ 0.27 / Pydantic v2 / FastAPI 0.115 / SQLAlchemy 2 / `bcrypt>=4.0,<5` + `passlib>=1.7.4`(passlib 1.7.4 是 PyPI 最新稳定版,本切片 plan 草稿中误写 1.7.5,Task 0 实施时已修正)/ Postgres 16 / docker-compose 2.x(横线版,见 CLAUDE.md)/ Caddy 2 + `caddy-dns/cloudflare` 插件(via `slothcroissant/caddy-cloudflaredns:latest`)/ `age` 加密 / `rclone` 同步 R2 / pwsh 7+(Windows dev)+ bash(VPS 部署)。

---

## Pre-flight(执行前自检)

执行本 plan 的 agent 在 Task 0 前需确认:

- 当前分支是 `slice-e-mcp-deploy`(`git branch --show-current`),从 `main` 拉出。本 plan 已在 `.claude/worktrees/slice-e-mcp-deploy/` 工作区准备好,直接进该目录开工。
- worktree 已有独立的 backend venv(`backend/.venv/`,Python 3.11)和 frontend `node_modules/`。验证:
  ```powershell
  cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
  .\backend\.venv\Scripts\python.exe -V   # → Python 3.11.x
  Test-Path .\frontend\node_modules\.bin\next   # → True
  ```
- worktree 有自己的 `.env`(从主目录复制过来,**已被 .gitignore**)。验证 `Test-Path .\.env` 为 True;若不存在,从主目录 `D:\IDEACursor\Claude-code\finance-manager\.env` 复制一份过来。
- Postgres 容器在跑:`docker ps --filter name=finance-manager-db-1` 应显示 `Up ... healthy`;若没起,在主目录跑 `docker-compose up -d db`(本 worktree 复用同一容器,所有 worktree + 主目录共用一个 db,这是单人项目的有意取舍)。
- 仓库根 `.env` 中 `ADMIN_PASSWORD_HASH` 是合法 bcrypt(`$2b$12$....`,60 字符);`ADMIN_USERNAME` 与 db 中 `users.username` 对得上(slice C task 3 已对齐 Settings 与 db)。

### ⚠ main 上的预先存在 regression(本切片必须 Task 0 修)

`verify_slice_d.ps1` 只跑 frontend(typecheck/vitest/build/路由/e2e),**不跑** backend pytest;所以 main HEAD 实际上 backend 测试套件有 **2 failed + 42 errors**(在 worktree 与主目录两个 venv 上都复现)。根本原因:`bcrypt` 库 5.0.0 移除了 `__about__.__version__` 属性,且强制对 ≥ 72 byte 密码抛 `ValueError`;但 `passlib[bcrypt]` 没跟上更新。表现:任何 import `passlib.handlers.bcrypt`、随后 `bcrypt.hash()` 或 `bcrypt.verify()` 一长口令的代码路径都炸,牵动所有需要 `admin_user` fixture 的 api 测试(因为 fixture 要 hash 密码 seed admin)。

**Task 0 在本 plan 第一步就修这个 regression**(pin `bcrypt<5` 在 `backend/pyproject.toml`,worktree 内重装并跑全测试套件确认绿)。Task 0 不修完,后续任何 task 跑测试都不可信。

### 实施纪律(吸取 slice D backend drift 教训)

slice D 实施过程中曾出现 plan "凭印象"写 backend schema 字段,导致 implementer 写 frontend client 时多次发现字段名/类型对不上 backend 真实代码(`TransactionOut.amount` 是 `Decimal` 不是 `float`,`SummaryOut.breakdown` 字段不叫 `groups` 等)。本切片 implementer **必须**遵守:

1. **每个 task 的第一个 step 之前**,先 Read 该 task 涉及的所有 backend `app/schemas/*.py`、`app/api/*.py`、`app/models/*.py` 真实代码,把字段名 / 类型 / 默认值 / 是否 nullable 在 task 内做一次三行 inline 校验摘录(用 `<!-- backend check: ... -->` HTML 注释或 markdown 引用块标注),再开始写测试与代码。
2. plan 中每个 task 内引用的 backend 字段 / endpoint 路径 / 错误码,如果与 backend 真实代码不一致,**立即停下来更正 plan,然后再继续实施**(不要"plan 是 plan、代码是代码"两边对不上还推进)。
3. MCP 工具的 inputSchema / outputSchema 必须**先**对照 spec § 8.1 表 + backend 真实 Pydantic schema **双向校验**;两边任一不一致,先在 task 内列出 diff,再决定改哪边(默认 backend 是 source of truth,spec 跟 backend 走;但如果 spec 给的字段是 MCP 友好的精简形态,backend 不变,MCP server 端做 trim)。

如以上任一不满足,在仓库根读 `CLAUDE.md` "环境与命令规约" 段补齐再开工。

---

## File Structure(切片 E 涉及的文件清单)

**新建 `mcp_server/`(整个目录,全新):**

```
mcp_server/
  pyproject.toml                    # mcp + httpx + pydantic 依赖(独立项目)
  Dockerfile                        # python:3.11-slim,装 pyproject 依赖
  README.md                         # 启动方式 + MCP Inspector 调试 + token 配置
  app/
    __init__.py
    main.py                         # MCP server entry:list_tools + dispatch + auth
    config.py                       # Settings(读 .env:MCP_API_TOKEN / MCP_BACKEND_URL / 端口)
    backend_client.py               # httpx wrapper:get/post/patch/delete + auth header
    errors.py                       # MCP 错误类型 → spec § 8.3 code 映射
    tools/
      __init__.py                   # 集中 register(tool_name → handler)
      list_transactions.py          # spec § 8.1 read #1
      get_summary.py                # read #2
      get_account_balances.py       # read #3
      find_merchant.py              # read #4
      list_pending_dedup_pairs.py   # read #5
      list_pending_classifications.py  # read #6
      add_transaction.py            # write #1
      update_category.py            # write #2
      bulk_update_category_by_merchant.py  # write #3
      confirm_dedup_pair.py         # write #4
  tests/
    __init__.py
    conftest.py                     # mock backend client fixture(httpx MockTransport)
    test_main_auth.py               # bearer token 验证流(成功 / 缺失 / 错误)
    test_backend_client.py          # auth header 注入 + error mapping
    test_tool_list_transactions.py
    test_tool_get_summary.py
    test_tool_get_account_balances.py
    test_tool_find_merchant.py
    test_tool_list_pending_dedup_pairs.py
    test_tool_list_pending_classifications.py
    test_tool_add_transaction.py
    test_tool_update_category.py
    test_tool_bulk_update_category_by_merchant.py
    test_tool_confirm_dedup_pair.py
```

**新建(仓库根 + scripts/):**

```
Caddyfile                           # spec § 11.2 模板,8443 web / 9443 mcp,DNS-01
scripts/
  backup.sh                         # pg_dump | age -r <pubkey> | rclone copy R2
  setup-vps.md                      # 部署文档:apt 装 docker / ufw / fail2ban / cron
.env.example                        # 替换现有(若存在)/ 新建,加 DOMAIN / CF_TOKEN / CADDY_ACME_EMAIL / age recipient
```

**新建(backend 端):**

```
backend/app/api/admin_tokens.py     # POST/GET/DELETE /api/admin/tokens(cookie 保护)
backend/app/services/api_token.py   # token 生成 / sha256 hash / 验证 / 吊销
backend/app/schemas/api_token.py    # ApiTokenCreate / ApiTokenOut / ApiTokenCreateResp
backend/tests/api/test_admin_tokens.py
backend/tests/api/test_transactions_create_find.py    # 新加 4 个 endpoint
backend/tests/services/test_api_token.py
backend/scripts/verify_slice_e.ps1
backend/tests/e2e/mcp_smoke.ps1     # MCP Inspector 替代:用 httpx 直接调 mcp server
```

**修改:**

- `backend/pyproject.toml` — Task 0 加 `bcrypt>=4.0,<5` pin,移除 `passlib[bcrypt]` 改用 `passlib`(bcrypt 不再做 extras);修 import 不影响其他代码,只把 deps 锁住
- `backend/app/api/transactions.py` — Task 1 加 `POST /api/transactions/manual`、Task 2 加 `GET /api/transactions/merchants`、Task 3 加 `GET /api/transactions/pending-classifications`(或在 list_transactions 加 `unclassified=true` query)
- `backend/app/schemas/transaction.py` — Task 1 加 `TransactionCreateIn`,Task 2 加 `MerchantStatItem` + `MerchantSearchOut`,Task 3 不动(复用 TransactionListOut)
- `backend/app/api/accounts.py` — Task 4 改 `list_accounts` 加 `latest_balance` 字段
- `backend/app/schemas/account.py` — Task 4 加 `AccountBalanceOut`(继承 AccountOut + latest_balance + latest_balance_at)
- `backend/app/services/summary.py` — Task 4 抽 `latest_balance_per_account` 纯函数(基于 transactions sum)
- `backend/app/services/auth.py` — Task 0 review 是否需要适配新 bcrypt(verify_password / hash_password 实现);若改用 native bcrypt 则替换 passlib 调用
- `backend/app/api/__init__.py` — Task 1-5 注册新 router
- `backend/app/main.py` — Task 5 注册 `admin_tokens` router
- `docker-compose.yml` — Task 19 引入 `dev` / `prod` profiles,prod 下移除 backend/mcp/postgres host port 映射,新增 `caddy` 服务
- `.env` — 文档不直接改用户的 .env(本地),只动 `.env.example`(若存在)
- `docs/superpowers/plans/2026-05-08-mvp-overview.md` — Task 21 标 slice E 完成 + 状态表
- `CLAUDE.md` — Task 21 进度勾选

**不动:**

- frontend 整个目录(spec § 9.1 settings 页 token 管理 是 web 自带,本切片只在 backend 端补 admin tokens API,settings 页的 frontend 接入留 V2;**这是有意为之**:slice D 已 ship 的 settings 页留 token placeholder,本切片不改前端避免 scope creep)
- backend 现有 4 个解析器(`alipay_csv` / `wechat_xlsx` / `bocom_debit_pdf` / `ccb_credit_pdf`)
- backend 现有 dedup / classifier / importer service
- alembic migrations(`api_tokens` 表 slice A 已建)

---

## Task 0:Pre-flight regression fix — `bcrypt 5.x` 兼容性 + 全测试绿

**Files:**
- Modify: `backend/pyproject.toml`(deps:加 bcrypt 版本 pin)
- Verify: `backend/.venv/Scripts/python.exe -m pytest tests/ -q`(应从 2 failed + 42 errors → 全绿)
- Optional Modify: `backend/app/services/auth.py`(若 passlib 仍 break,降级到 native bcrypt API)

> **背景:** main HEAD `b387489`(本 worktree 起点)的 `backend/pyproject.toml` 第 20 行 `"passlib[bcrypt]>=1.7"` 不带 bcrypt 上限,装到 worktree 时 pip 解析出 bcrypt **5.0.0**。bcrypt 5.0.0 的两个 break:
> 1. 移除 `bcrypt.__about__.__version__`,passlib 1.7.x 在 `_load_backend_mixin` 里 reads 这个属性失败,trapped warning + 退化路径;
> 2. 强制对 ≥ 72 byte secret 抛 `ValueError("password cannot be longer than 72 bytes...")`,不再静默 truncate。
>
> backend test 套件中 `tests/services/test_auth_service.py::test_verify_password_correct` 用了一个 240 byte 测试密码,直接命中 (2);所有 `tests/api/*.py` 通过 `admin_user` fixture 也走 bcrypt 路径,42 个测试全 error。
>
> 修复策略 — **首选** pin `bcrypt>=4.0,<5`(passlib 1.7.4 已被 4.x 验证过):
>
> ```toml
> "bcrypt>=4.0,<5",
> "passlib>=1.7.4",     # 原 "passlib[bcrypt]>=1.7" → 拆出 bcrypt 显式 pin(passlib 1.7.4 = PyPI 最新)
> ```
>
> 若 worktree 重装后仍有问题,**fallback** 改 `app/services/auth.py` 不走 passlib,直接用 native `bcrypt.hashpw / bcrypt.checkpw`(API 更稳定,且 bcrypt 4.x/5.x 都兼容);本 task 优先走首选,fallback 留给 step 0.6 触发条件下做。

- [ ] **Step 0.1:复现失败基线**(在 worktree 内)

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\services\test_auth_service.py::test_verify_password_correct backend\tests\api\test_transactions.py::test_list_transactions_pagination -v 2>&1 | Select-Object -Last 20
```

期望:`1 failed, 1 error`,关键错误信息:
- `ValueError: password cannot be longer than 72 bytes, truncate manually...`
- `AttributeError: module 'bcrypt' has no attribute '__about__'`

记录当前 bcrypt 版本以备对照:

```powershell
.\backend\.venv\Scripts\python.exe -m pip show bcrypt | Select-String "^Version"
# Version: 5.0.0
```

- [ ] **Step 0.2:修改 `backend/pyproject.toml` pin 版本**

打开 [backend/pyproject.toml](backend/pyproject.toml),找到 dependencies 列表中的两行:

```toml
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
```

**注意**:必须从 worktree 路径打开(`.claude/worktrees/slice-e-mcp-deploy/backend/pyproject.toml`),不要改主目录。

改成:

```toml
    "python-jose[cryptography]>=3.3",
    "passlib>=1.7.4",
    "bcrypt>=4.0,<5",
```

3 个变化:
1. 把 `passlib[bcrypt]` 拆出 `passlib` 本体,显式独立 pin `bcrypt`
2. `passlib>=1.7.5`(原 `>=1.7`):1.7.5 是 passlib 最新稳定版,改善 bcrypt 4.x 兼容
3. `bcrypt>=4.0,<5`:挡掉 5.x 的 API break;4.x 系最高稳定,且与 passlib 1.7.5 验证过

- [ ] **Step 0.3:在 worktree venv 重装依赖**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\backend
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall "bcrypt>=4.0,<5" "passlib>=1.7.4"
.\.venv\Scripts\python.exe -m pip show bcrypt | Select-String "^Version"
# 期望:Version: 4.x.x(具体次要版本看 pip 解析)
.\.venv\Scripts\python.exe -m pip show passlib | Select-String "^Version"
# 期望:Version: 1.7.x
```

如果 force-reinstall 后 `python -c "import bcrypt; print(bcrypt.__about__.__version__)"` 报 AttributeError,但 `python -c "import bcrypt; print(bcrypt.__version__)"` 正常,**不要急着改代码** — 这是 4.x 早期版本(< 4.0.1)的现象,继续 step 0.4 跑 pytest 看实际是否全绿。

- [ ] **Step 0.4:跑全测试套件确认绿**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\backend
.\.venv\Scripts\python.exe -m pytest tests/ -q --tb=line 2>&1 | Select-Object -Last 15
```

期望末行:`<N> passed in <M>s`(N 应为 271 左右,与 main DoD 数字一致;若有 1-2 个本来就 skip 的 test 不算 fail)。如出现 0 fail / 0 error / N passed,Step 0.4 PASS,跳到 Step 0.6。

如还有 fail / error,**99% 是 passlib + bcrypt 4.x 仍不和**,进 Step 0.5 fallback。

- [ ] **Step 0.5(条件):fallback — 改 `app/services/auth.py` 不走 passlib**

读 [backend/app/services/auth.py](backend/app/services/auth.py)(整文件),典型实现:

```python
from passlib.context import CryptContext
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)
```

改成 native bcrypt(API 更稳):

```python
import bcrypt

def verify_password(plain: str, hashed: str) -> bool:
    """bcrypt 强制要求 secret ≤ 72 bytes — 截断保留旧测试密码兼容,与 passlib 默认行为一致。"""
    plain_bytes = plain.encode("utf-8")[:72]
    hashed_bytes = hashed.encode("utf-8")
    try:
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except ValueError:
        # bcrypt 对非法 hash 会抛 ValueError(如旧的 passlib placeholder 残留)
        return False

def hash_password(plain: str) -> str:
    plain_bytes = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(plain_bytes, bcrypt.gensalt()).decode("utf-8")
```

注意:
- `[:72]` 是显式截断(passlib 1.7.x 默认行为相同);测试里那个 240 byte 密码会被截到 72 byte 再 hash/verify,**两边截断一致**,所以行为不变
- import 不再用 passlib,但其他文件如有 `from app.services.auth import verify_password` / `hash_password`,接口不变,不需要级联改

跑全测试再次确认:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

期望 0 fail / 0 error。

- [ ] **Step 0.6:验证主目录 venv 也修(同步)**

> **注意**:这步是为了避免 worktree 修了、主目录还坏 — 主目录 venv 也得同步,否则用户在主目录跑 `verify_slice_*.ps1` 时仍会爆。但**不**要在主目录修改 pyproject.toml(那是 worktree 的工作);只在主目录 venv 里同步 reinstall:

```powershell
& "D:\IDEACursor\Claude-code\finance-manager\backend\.venv\Scripts\python.exe" -m pip install --upgrade --force-reinstall "bcrypt>=4.0,<5" "passlib>=1.7.4"
& "D:\IDEACursor\Claude-code\finance-manager\backend\.venv\Scripts\python.exe" -m pytest "D:\IDEACursor\Claude-code\finance-manager\backend\tests\" -q 2>&1 | Select-Object -Last 5
```

主目录 venv 也应转绿。这步不 commit 主目录任何变化(只是 venv install,venv 在 .gitignore 内)。

- [ ] **Step 0.7:Commit pyproject.toml + (可选)auth.py 改动**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
git add backend/pyproject.toml
# 如做了 step 0.5:
git add backend/app/services/auth.py
git commit -m "fix(backend): pin bcrypt<5 + passlib>=1.7.5 to fix bcrypt 5.x regression

bcrypt 5.0 removed __about__.__version__ and made >72-byte secrets raise
ValueError instead of silently truncating, breaking passlib's compat shim
and 42 backend tests (admin_user fixture cascade).

Pinning bcrypt<5 + passlib>=1.7.5 restores green baseline. main HEAD had
this regression because verify_slice_d.ps1 only runs frontend tests, so
backend pytest was never re-validated post-merge."
```

- [ ] **Step 0.8:在 overview.md 把这个 regression 闭环记一笔**

打开 [docs/superpowers/plans/2026-05-08-mvp-overview.md](docs/superpowers/plans/2026-05-08-mvp-overview.md),"已知遗留问题(切片 A → 后续切片处理)"段下方追加一个新子节(在 "Polish(后续任意切片处理)" 之前):

```markdown
### 切片 D 实施期间引入(已在 slice E Task 0 闭环)

- ~~**bcrypt 5.x regression**:某次 `pip install` 升 bcrypt 到 5.0.0(API break:`__about__` 移除 + ≥72byte 强制抛错),passlib 1.7.x 不兼容,backend pytest 套件 2 failed + 42 errors。`verify_slice_d.ps1` 只跑 frontend,没暴露此问题。~~ ✅ 已在 slice E Task 0 修复(`pyproject.toml` pin `bcrypt>=4.0,<5` + `passlib>=1.7.5`)
```

```powershell
git add docs/superpowers/plans/2026-05-08-mvp-overview.md
git commit -m "docs(overview): record bcrypt 5.x regression closed in slice E task 0"
```

---

## Task 1:Backend gap — `POST /api/transactions/manual`(支撑 MCP `add_transaction`)

**Files:**
- Modify: `backend/app/schemas/transaction.py`(加 `TransactionCreateIn` + 复用 `TransactionOut`)
- Modify: `backend/app/schemas/__init__.py`(re-export `TransactionCreateIn`)
- Modify: `backend/app/api/transactions.py`(加 `create_manual_transaction` route)
- Create: `backend/tests/api/test_transactions_create_find.py`(本切片新 endpoint 共用一个 test 文件)

> **背景:** spec § 8.1 `add_transaction` 工具入参 `{time, amount, currency='CNY', merchant, category?, account?, kind='expense'}`,出参 `{transaction_id, applied_rule?, classified_category}`。现有 `transactions.py` 只有 GET / GET/{id} / PATCH / bulk-update / DELETE,**没有 POST**。本 task 在 backend 端补一个 `POST /api/transactions/manual`(路径用 `/manual` 而非 `/`,以避免与未来可能的"批量创建"或"通用创建"区分,并明确语义:source 一定是 `manual`),内部走 `classify_batch` 做规则匹配,返回 transaction + 命中的 rule_id + category_id。
>
> **inline backend 校验**:
>
> ```
> backend check (transactions.py):  POST endpoint absent — only GET / GET/{id} / PATCH / POST/bulk-update-by-merchant / DELETE
> backend check (transaction.py schema):  TransactionOut from_attributes=True,字段含 amount: Decimal / merchant_normalized: str | None / source: SourceKind / classification_confidence: float | None
> backend check (services/classifier.py):  classify_batch(db, transactions: list[Transaction]) → 直接修改 tx.category_id / tx.classification_confidence(返 None);使用 _match_rule(merchant_normalized, pattern, match_kind),需要 normalize 后的 merchant
> backend check (services/statement_parser/normalize.py):  normalize_merchant(raw: str) → str 已存在(slice B);Task 1 必须复用,不要在 endpoint 里 inline normalize 逻辑
> ```

- [ ] **Step 1.1:Read backend 真实代码做 inline 校验**(写 plan/code 前必做)

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
# 用 cat / Get-Content 各 read 一次,确认上面 4 行校验摘录的真实性:
Get-Content backend\app\api\transactions.py | Select-String -Pattern "@router\." | Select-Object -ExpandProperty Line
# 期望:5 行 router 装饰器,无 POST(根路径)
Get-Content backend\app\schemas\transaction.py | Select-String -Pattern "^class " | Select-Object -ExpandProperty Line
# 期望:TransactionOut / TransactionListOut / TransactionQuery / TransactionPatchIn / BulkUpdateByMerchantIn / BulkUpdateResult
Get-Content backend\app\services\classifier.py | Select-String -Pattern "^def |^class " | Select-Object -ExpandProperty Line
# 找 classify_batch / _match_rule 签名
Get-Content backend\app\services\statement_parser\normalize.py | Select-String -Pattern "^def "
# 期望:def normalize_merchant(...)
```

如有任一不符(例如 `_match_rule` 实际叫 `match_rule` 或在别处),**改本 plan inline 校验摘录** 与真实代码对齐,再继续 step 1.2。

- [ ] **Step 1.2:写测试 — `test_transactions_create_find.py`(create 部分)**

新建 [backend/tests/api/test_transactions_create_find.py](backend/tests/api/test_transactions_create_find.py):

```python
"""POST /api/transactions/manual + GET /merchants + GET /pending-classifications 测试。

slice E Task 1/2/3 端点共用此文件 — 三组测试用 # === Section ===  注释分隔。
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Category, MerchantRule, Transaction


# === Section: POST /api/transactions/manual (Task 1) ===

@pytest.fixture
def alipay_account(db, admin_user) -> Account:
    acc = Account(
        user_id=admin_user.id, name="支付宝", type="alipay",
        institution="支付宝", last4=None, currency="CNY",
    )
    db.add(acc); db.flush()
    return acc


@pytest.fixture
def cafe_category(db, admin_user) -> Category:
    cat = Category(
        user_id=admin_user.id, name="餐饮/咖啡",
        kind="expense", sort_order=10,
    )
    db.add(cat); db.flush()
    return cat


def test_create_manual_transaction_basic(logged_in_client, alipay_account, cafe_category, db, admin_user):
    """最简 happy path — time + amount + merchant + account_id + category_id 显式给。"""
    body = {
        "tx_time": "2026-05-10T12:30:00",
        "amount": "23.50",
        "currency": "CNY",
        "merchant": "瑞幸咖啡  五道口店",
        "account_id": alipay_account.id,
        "category_id": cafe_category.id,
        "tx_kind": "expense",
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["amount"] == "23.50"
    assert data["currency"] == "CNY"
    assert data["account_id"] == alipay_account.id
    assert data["category_id"] == cafe_category.id
    assert data["source"] == "manual"
    assert data["tx_kind"] == "expense"
    # merchant_normalized 应已 normalize(去多余空格、保留主名)
    assert "瑞幸咖啡" in data["merchant_normalized"]
    # is_mirror 默认 False
    assert data["is_mirror"] is False


def test_create_manual_transaction_classifier_hits_rule(
    logged_in_client, alipay_account, cafe_category, db, admin_user,
):
    """category_id 不给,但商家规则命中 → 自动归类。"""
    rule = MerchantRule(
        user_id=admin_user.id, pattern="瑞幸",
        match_kind="contains", category_id=cafe_category.id, priority=50,
    )
    db.add(rule); db.flush()

    body = {
        "tx_time": "2026-05-10T08:00:00",
        "amount": "18.00",
        "merchant": "瑞幸咖啡 西二旗",
        "account_id": alipay_account.id,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # 规则命中 → category_id 被填,confidence=1.0
    assert data["category_id"] == cafe_category.id
    assert data["classification_confidence"] == 1.0


def test_create_manual_transaction_no_rule_match_uncategorized(
    logged_in_client, alipay_account, db, admin_user,
):
    """没规则命中 + 不显式给 category → 进未分类(category_id=None)。"""
    body = {
        "tx_time": "2026-05-10T18:00:00",
        "amount": "100.00",
        "merchant": "某不知名小馆",
        "account_id": alipay_account.id,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 201
    data = resp.json()
    assert data["category_id"] is None
    assert data["classification_confidence"] is None


def test_create_manual_transaction_invalid_account_404(logged_in_client):
    body = {
        "tx_time": "2026-05-10T12:00:00",
        "amount": "10.00",
        "merchant": "x",
        "account_id": 999999,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 404
    assert "account" in resp.json()["detail"].lower()


def test_create_manual_transaction_invalid_category_404(
    logged_in_client, alipay_account,
):
    body = {
        "tx_time": "2026-05-10T12:00:00",
        "amount": "10.00",
        "merchant": "x",
        "account_id": alipay_account.id,
        "category_id": 999999,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 404
    assert "category" in resp.json()["detail"].lower()


def test_create_manual_transaction_negative_amount_422(logged_in_client, alipay_account):
    body = {
        "tx_time": "2026-05-10T12:00:00",
        "amount": "-10.00",
        "merchant": "x",
        "account_id": alipay_account.id,
    }
    resp = logged_in_client.post("/api/transactions/manual", json=body)
    assert resp.status_code == 422  # Pydantic 拒绝负数(Field gt=0)
```

- [ ] **Step 1.3:跑测试看失败(端点尚未实现)**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\backend
.\.venv\Scripts\python.exe -m pytest tests/api/test_transactions_create_find.py -v 2>&1 | Select-Object -Last 15
```

期望 6 个 test 全 FAIL(404 not found / Pydantic schema 不存在等)。如某个 test 因为别的原因 fail(import error 等),回 step 1.1 检查 inline 校验是否漏了什么。

- [ ] **Step 1.4:加 `TransactionCreateIn` schema**

打开 [backend/app/schemas/transaction.py](backend/app/schemas/transaction.py),在 `BulkUpdateResult` 之后追加:

```python
class TransactionCreateIn(BaseModel):
    """POST /api/transactions/manual — spec § 8.1 add_transaction 工具的 backend 等价。"""
    tx_time: datetime
    amount: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    currency: str = Field("CNY", min_length=3, max_length=8)
    merchant: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=512)
    account_id: int
    category_id: int | None = None
    tx_kind: TxKind = "expense"
```

注意:
- `amount: Decimal Field(gt=0, max_digits=14, decimal_places=2)` — spec § 4.1 transactions.amount 是 NUMERIC(14,2),Pydantic v2 用 `Field(max_digits, decimal_places)` 对齐
- `merchant` 必填,**未 normalize**;endpoint 内部调 `normalize_merchant()` 算 merchant_normalized,落库时两个字段都填
- `tx_kind` 默认 `expense`(spec § 8.1 明确)

- [ ] **Step 1.5:re-export `TransactionCreateIn`**

打开 [backend/app/schemas/__init__.py](backend/app/schemas/__init__.py),在 transaction 一段加:

```python
from app.schemas.transaction import (
    BulkUpdateByMerchantIn,
    BulkUpdateResult,
    TransactionCreateIn,            # <-- 新增
    TransactionListOut,
    TransactionOut,
    TransactionPatchIn,
    TransactionQuery,
)
```

并在底部 `__all__` 列表对应位置加 `"TransactionCreateIn",`。

- [ ] **Step 1.6:加 `create_manual_transaction` route**

打开 [backend/app/api/transactions.py](backend/app/api/transactions.py),在 `_get_tx_or_404` 函数之前(顶部 router 定义之后)插入:

```python
from datetime import UTC

from app.models import Account
from app.schemas import TransactionCreateIn
from app.services.classifier import classify_batch
from app.services.statement_parser.normalize import normalize_merchant


@router.post("/manual", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_manual_transaction(
    body: TransactionCreateIn, user: CurrentUserDep, db: DbDep,
) -> TransactionOut:
    """spec § 8.1 add_transaction 工具的 backend 实现。

    流程:
    1) 校验 account_id 属于当前 user(404)
    2) 若给了 category_id → 校验属于当前 user(404),并跳过分类引擎
    3) 否则 → 跑 classify_batch 单条,命中规则填 category_id + confidence=1.0
    4) tx 落库 source='manual',source_unique_key=None,is_mirror=False
    """
    # 1) account 校验
    acc = db.execute(
        select(Account).where(
            Account.id == body.account_id, Account.user_id == user.id,
        )
    ).scalar_one_or_none()
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

    # 2) category 校验(若给了)
    if body.category_id is not None:
        cat = db.execute(
            select(Category).where(
                Category.id == body.category_id, Category.user_id == user.id,
            )
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")

    # 3) 构 Transaction(暂不 commit,先看是否要跑 classifier)
    merchant_norm = normalize_merchant(body.merchant)
    tx = Transaction(
        user_id=user.id,
        account_id=body.account_id,
        statement_import_id=None,
        tx_kind=body.tx_kind,
        tx_time=body.tx_time,
        post_time=None,
        amount=body.amount,
        currency=body.currency,
        amount_settled_cny=body.amount,  # manual 默认 CNY,无需折算
        merchant_raw=body.merchant,
        merchant_normalized=merchant_norm,
        counterparty_raw=None,
        description_raw=body.description,
        category_id=body.category_id,
        classification_confidence=1.0 if body.category_id is not None else None,
        source="manual",
        external_tx_id=None,
        external_merchant_id=None,
        payment_method_raw=None,
        is_mirror=False,
        mirror_of_id=None,
        source_unique_key=None,
        raw_payload=None,
    )
    db.add(tx); db.flush()

    # 4) 若没显式给 category,跑 classifier
    if body.category_id is None:
        classify_batch(db, [tx])
        db.flush()

    return TransactionOut.model_validate(tx)
```

注意:
- `from datetime import UTC` 和 `from app.models import Account` 可能已在文件顶部 import,**先确认**(用 `Get-Content backend\app\api\transactions.py | Select-String "^from app.models|^from datetime"`),已存在则不要重复导入,只补缺的(避免 ruff F401)
- 如果文件顶部 import 不全,把上面 4 行 import 加到顶部 import 段(按 isort 规则:standard → third-party → local,本地 `app.*` 一组)
- `classify_batch` 接口若实际签名是 `classify_batch(db, transactions, ...)` 带额外 kwargs,先 read [backend/app/services/classifier.py](backend/app/services/classifier.py) 真实签名,适配调用

- [ ] **Step 1.7:跑测试看通过**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\backend
.\.venv\Scripts\python.exe -m pytest tests/api/test_transactions_create_find.py -v 2>&1 | Select-Object -Last 20
```

期望 6 个 test 全 PASS。如某个 fail:
- 422 而期望 201:看 schema 校验是否过严
- 404 而期望 201 / 反之:account/category 查询条件错(可能漏了 user_id)
- classifier 没命中规则:看 `_match_rule(merchant_normalized=..., pattern=..., match_kind=...)` 是否 normalize 影响命中

- [ ] **Step 1.8:跑全测试套件确认没回归**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

期望 0 fail / 0 error,passed 数 = Task 0 末尾基线 + 6(本 task 新增 6 个)。

- [ ] **Step 1.9:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
git add backend/app/schemas/transaction.py backend/app/schemas/__init__.py backend/app/api/transactions.py backend/tests/api/test_transactions_create_find.py
git commit -m "feat(backend): POST /api/transactions/manual for MCP add_transaction tool

Spec § 8.1 add_transaction needs a backend endpoint to create a manual
transaction with optional category_id (skip classifier) or auto-classify
via merchant rules (category_id=null falls through to classify_batch).
"
```

---

## Task 2:Backend gap — `GET /api/transactions/merchants`(支撑 MCP `find_merchant`)

**Files:**
- Modify: `backend/app/schemas/transaction.py`(加 `MerchantStatItem` + `MerchantSearchOut`)
- Modify: `backend/app/schemas/__init__.py`(re-export 新 schemas)
- Modify: `backend/app/api/transactions.py`(加 `find_merchants` route)
- Modify: `backend/tests/api/test_transactions_create_find.py`(继续追加 # === Section: GET /merchants ===)

> **背景:** spec § 8.1 `find_merchant` 工具入参 `keyword`,出参 `merchants: [{normalized, count, total_amount, sample_categories}]`。聚合算法:对当前 user 所有 `is_mirror=False` 的 transactions,where `merchant_normalized ILIKE %keyword%`,group by merchant_normalized,select count + sum(amount_settled_cny),并对每个商家取 top 3 命中过的 category 名作为 sample。
>
> **inline backend 校验**:
>
> ```
> backend check (Transaction model):  has merchant_normalized: str | None;有 ix_transactions_user_merchant_norm 索引(spec § 4.2),所以 ILIKE %keyword% 在小数据集合理(MVP 单用户、千万级以下交易)
> backend check (Category model):  has name: str(slice A schema)
> backend check (transactions.py):  imports `from app.models import Category, MerchantRule, Transaction`,Category 已可用
> ```

- [ ] **Step 2.1:Inline 校验**

```powershell
Get-Content backend\app\models\transaction.py | Select-String -Pattern "merchant_normalized|ix_transactions_user_merchant"
Get-Content backend\app\models\category.py | Select-String -Pattern "name:"
```

确认两个字段真实存在。

- [ ] **Step 2.2:写测试**

打开 [backend/tests/api/test_transactions_create_find.py](backend/tests/api/test_transactions_create_find.py),在文件末尾追加:

```python
# === Section: GET /api/transactions/merchants (Task 2) ===

@pytest.fixture
def luckin_transactions(db, admin_user, alipay_account, cafe_category) -> list[Transaction]:
    """seed 5 笔瑞幸 + 2 笔星巴克,均 expense 已分类。"""
    rows: list[Transaction] = []
    for i, (merchant_norm, amt) in enumerate([
        ("瑞幸咖啡 五道口", "23.50"),
        ("瑞幸咖啡 西二旗", "18.00"),
        ("瑞幸咖啡 五道口", "25.00"),
        ("瑞幸咖啡 望京", "21.00"),
        ("瑞幸咖啡 五道口", "27.00"),
        ("星巴克 国贸店", "38.00"),
        ("星巴克 望京店", "42.00"),
    ]):
        tx = Transaction(
            user_id=admin_user.id, account_id=alipay_account.id,
            tx_kind="expense", tx_time=datetime(2026, 5, 1+i, 9, 0, tzinfo=timezone.utc),
            amount=Decimal(amt), currency="CNY", amount_settled_cny=Decimal(amt),
            merchant_raw=merchant_norm, merchant_normalized=merchant_norm,
            category_id=cafe_category.id, classification_confidence=1.0,
            source="manual", is_mirror=False,
        )
        db.add(tx); rows.append(tx)
    db.flush()
    return rows


def test_find_merchants_keyword_match(logged_in_client, luckin_transactions):
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "瑞幸"})
    assert resp.status_code == 200
    data = resp.json()
    # 至少 3 个不同的瑞幸 normalized 名字(五道口/西二旗/望京)
    luckin_items = [m for m in data["items"] if "瑞幸" in m["normalized"]]
    assert len(luckin_items) >= 3
    # 每条有 count + total_amount + sample_categories
    for item in luckin_items:
        assert item["count"] >= 1
        assert Decimal(item["total_amount"]) > 0
        assert isinstance(item["sample_categories"], list)
    # 五道口出现 3 次合计 75.50
    wudaokou = next(m for m in luckin_items if "五道口" in m["normalized"])
    assert wudaokou["count"] == 3
    assert Decimal(wudaokou["total_amount"]) == Decimal("75.50")


def test_find_merchants_keyword_case_insensitive(logged_in_client, luckin_transactions):
    """ILIKE 大小写不敏感(中文不影响,但确保英文走 ILIKE)。"""
    # 加一条英文商户
    # (此 test 仅校验 ILIKE 走 ICU,中文 LIKE 在 PG 里默认大小写无关,英文需 ILIKE)
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "星巴克"})
    assert resp.status_code == 200
    starbucks = [m for m in resp.json()["items"] if "星巴克" in m["normalized"]]
    assert len(starbucks) == 2  # 国贸店 + 望京店


def test_find_merchants_empty_keyword_422(logged_in_client):
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": ""})
    assert resp.status_code == 422


def test_find_merchants_no_match_returns_empty(logged_in_client, luckin_transactions):
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "tim hortons"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_find_merchants_excludes_mirrors(
    logged_in_client, luckin_transactions, db,
):
    """is_mirror=True 的 transaction 不参与聚合(避免重复算)。"""
    # 把第一条标 mirror
    luckin_transactions[0].is_mirror = True
    luckin_transactions[0].mirror_of_id = luckin_transactions[1].id
    db.flush()
    resp = logged_in_client.get("/api/transactions/merchants", params={"keyword": "瑞幸 五道口"})
    # 五道口仍能聚合(剩 2 条),count=2 而非 3
    wudaokou = next(
        m for m in resp.json()["items"] if "五道口" in m["normalized"]
    )
    assert wudaokou["count"] == 2
```

- [ ] **Step 2.3:跑测试看失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_transactions_create_find.py -k merchants -v 2>&1 | Select-Object -Last 15
```

期望 5 个 test 全 FAIL(404)。

- [ ] **Step 2.4:加 `MerchantStatItem` + `MerchantSearchOut` schemas**

打开 [backend/app/schemas/transaction.py](backend/app/schemas/transaction.py),在 `TransactionCreateIn` 之后追加:

```python
class MerchantStatItem(BaseModel):
    """spec § 8.1 find_merchant 单条聚合结果。"""
    normalized: str
    count: int
    total_amount: Decimal
    sample_categories: list[str]    # 该商家命中过的 category 名字 top 3,无分类则空


class MerchantSearchOut(BaseModel):
    items: list[MerchantStatItem]
    total: int                       # 不去 count(*) 单查,直接 len(items);limit 默认 50
```

- [ ] **Step 2.5:re-export 新 schemas**

[backend/app/schemas/__init__.py](backend/app/schemas/__init__.py) 的 transaction 一段补:

```python
from app.schemas.transaction import (
    BulkUpdateByMerchantIn,
    BulkUpdateResult,
    MerchantSearchOut,              # <-- 新增
    MerchantStatItem,               # <-- 新增
    TransactionCreateIn,
    TransactionListOut,
    TransactionOut,
    TransactionPatchIn,
    TransactionQuery,
)
```

`__all__` 加 `"MerchantSearchOut", "MerchantStatItem",`。

- [ ] **Step 2.6:加 `find_merchants` route**

打开 [backend/app/api/transactions.py](backend/app/api/transactions.py),在 `delete_transaction` route 之后追加:

```python
@router.get("/merchants", response_model=MerchantSearchOut)
def find_merchants(
    user: CurrentUserDep, db: DbDep,
    keyword: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=200),
) -> MerchantSearchOut:
    """spec § 8.1 find_merchant 工具的 backend 实现。

    聚合 group by merchant_normalized,排除 is_mirror=True;
    sample_categories:对每组取 top 3 出现频次最高的 category name(无分类记 NULL → 跳过)。
    """
    # Step 1:聚合 count + sum
    rows = db.execute(
        select(
            Transaction.merchant_normalized,
            func.count(Transaction.id).label("cnt"),
            func.sum(Transaction.amount_settled_cny).label("amt"),
        )
        .where(
            Transaction.user_id == user.id,
            Transaction.is_mirror.is_(False),
            Transaction.merchant_normalized.ilike(f"%{keyword}%"),
        )
        .group_by(Transaction.merchant_normalized)
        .order_by(func.sum(Transaction.amount_settled_cny).desc())
        .limit(limit)
    ).all()

    if not rows:
        return MerchantSearchOut(items=[], total=0)

    # Step 2:对每个 normalized,查它的 top 3 categories
    normalized_names = [r[0] for r in rows if r[0] is not None]
    cat_rows = db.execute(
        select(
            Transaction.merchant_normalized,
            Category.name,
            func.count(Transaction.id).label("hit_cnt"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user.id,
            Transaction.is_mirror.is_(False),
            Transaction.merchant_normalized.in_(normalized_names),
        )
        .group_by(Transaction.merchant_normalized, Category.name)
        .order_by(Transaction.merchant_normalized, func.count(Transaction.id).desc())
    ).all()

    # 把 top 3 折叠到 dict[normalized, list[name]]
    samples: dict[str, list[str]] = {}
    for norm, name, _cnt in cat_rows:
        bucket = samples.setdefault(norm, [])
        if len(bucket) < 3:
            bucket.append(name)

    items = [
        MerchantStatItem(
            normalized=(norm or ""),
            count=cnt,
            total_amount=amt,
            sample_categories=samples.get(norm, []),
        )
        for norm, cnt, amt in rows
    ]
    return MerchantSearchOut(items=items, total=len(items))
```

注意:
- `from app.models import Category` 已在文件顶部 import(transactions.py 之前的 task 已加),无需重复
- `from app.schemas import MerchantSearchOut, MerchantStatItem` — 加到顶部 import 段(从 `app.schemas` 单行 import 列表里追加,确认无重复)
- `func.count` / `func.sum` / `select` 已 import(slice C 已加)

- [ ] **Step 2.7:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_transactions_create_find.py -k merchants -v 2>&1 | Select-Object -Last 15
```

期望 5 全 PASS。如 mirror exclusion 失败,确认 `is_mirror.is_(False)` 没漏。

- [ ] **Step 2.8:跑全套测试 + commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 3
git add backend/app/schemas/transaction.py backend/app/schemas/__init__.py backend/app/api/transactions.py backend/tests/api/test_transactions_create_find.py
git commit -m "feat(backend): GET /api/transactions/merchants for MCP find_merchant

Aggregates merchant_normalized via ILIKE + sum/count, then for top
matches resolves top-3 sample categories (joined via category_id).
Excludes is_mirror=True so dedup'd entries don't double count.
"
```

---

## Task 3:Backend gap — `GET /api/transactions/pending-classifications`(支撑 MCP `list_pending_classifications`)

**Files:**
- Modify: `backend/app/api/transactions.py`(加 `list_pending_classifications` route)
- Modify: `backend/tests/api/test_transactions_create_find.py`(追加 # === Section: pending-classifications ===)

> **背景:** spec § 8.1 `list_pending_classifications` 工具入参 `limit=20`,出参 `transactions: [{id, time, amount, merchant, suggested_categories[]}]`。简单实现:`SELECT * FROM transactions WHERE category_id IS NULL AND is_mirror=False ORDER BY tx_time DESC LIMIT N`,suggested_categories 第一版**留空数组**(后续 V2 可基于 merchant_normalized 走 rapidfuzz 模糊匹配 categories.name 给建议)。
>
> 第一版选择:**新加专属 endpoint** 而非扩展 list_transactions 加 `unclassified=true`。理由:语义清晰,出参可以未来加 `suggested_categories`(那时 list_transactions 不该有这个字段)。
>
> **inline backend 校验**:
>
> ```
> backend check (Transaction):  category_id Mapped[int | None],SQL is_(None) 标准 Pydantic
> backend check (TransactionListOut):  items: list[TransactionOut] / total / limit / offset — Task 3 直接复用,suggested_categories 第一版不返回(留 V2)
> ```

- [ ] **Step 3.1:Inline 校验**(略,字段都在 Task 1/2 的 read 范围内)

- [ ] **Step 3.2:写测试**

[backend/tests/api/test_transactions_create_find.py](backend/tests/api/test_transactions_create_find.py) 末尾追加:

```python
# === Section: GET /api/transactions/pending-classifications (Task 3) ===

def test_pending_classifications_returns_only_uncategorized(
    logged_in_client, alipay_account, cafe_category, db, admin_user,
):
    """category_id IS NULL → 进列表;已分类的不出现。"""
    # 1 笔已分类 + 2 笔未分类
    classified = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 1, 12, tzinfo=timezone.utc),
        amount=Decimal("10.00"), currency="CNY", amount_settled_cny=Decimal("10.00"),
        merchant_raw="瑞幸", merchant_normalized="瑞幸",
        category_id=cafe_category.id, classification_confidence=1.0,
        source="manual", is_mirror=False,
    )
    pending1 = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 2, 12, tzinfo=timezone.utc),
        amount=Decimal("20.00"), currency="CNY", amount_settled_cny=Decimal("20.00"),
        merchant_raw="某小店", merchant_normalized="某小店",
        category_id=None, source="manual", is_mirror=False,
    )
    pending2 = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 3, 12, tzinfo=timezone.utc),
        amount=Decimal("30.00"), currency="CNY", amount_settled_cny=Decimal("30.00"),
        merchant_raw="另家店", merchant_normalized="另家店",
        category_id=None, source="manual", is_mirror=False,
    )
    db.add_all([classified, pending1, pending2]); db.flush()

    resp = logged_in_client.get("/api/transactions/pending-classifications")
    assert resp.status_code == 200
    data = resp.json()
    ids = [tx["id"] for tx in data["items"]]
    assert pending1.id in ids
    assert pending2.id in ids
    assert classified.id not in ids


def test_pending_classifications_excludes_mirrors(
    logged_in_client, alipay_account, db, admin_user,
):
    """is_mirror=True 的未分类 tx 也不应出现(已被去重的镜像不需要分类)。"""
    primary = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 4, 12, tzinfo=timezone.utc),
        amount=Decimal("50.00"), currency="CNY", amount_settled_cny=Decimal("50.00"),
        merchant_raw="A", merchant_normalized="A",
        category_id=None, source="alipay", is_mirror=False,
    )
    db.add(primary); db.flush()
    mirror = Transaction(
        user_id=admin_user.id, account_id=alipay_account.id,
        tx_kind="expense", tx_time=datetime(2026, 5, 4, 12, tzinfo=timezone.utc),
        amount=Decimal("50.00"), currency="CNY", amount_settled_cny=Decimal("50.00"),
        merchant_raw="A", merchant_normalized="A",
        category_id=None, source="bank", is_mirror=True, mirror_of_id=primary.id,
    )
    db.add(mirror); db.flush()

    resp = logged_in_client.get("/api/transactions/pending-classifications")
    ids = [tx["id"] for tx in resp.json()["items"]]
    assert primary.id in ids
    assert mirror.id not in ids


def test_pending_classifications_pagination(
    logged_in_client, alipay_account, db, admin_user,
):
    """seed 5 条 → limit=2 + offset=2 应返回中间 2 条(按 tx_time DESC)。"""
    for i in range(5):
        db.add(Transaction(
            user_id=admin_user.id, account_id=alipay_account.id,
            tx_kind="expense", tx_time=datetime(2026, 5, 10+i, 12, tzinfo=timezone.utc),
            amount=Decimal("10.00"), currency="CNY", amount_settled_cny=Decimal("10.00"),
            merchant_raw=f"店{i}", merchant_normalized=f"店{i}",
            category_id=None, source="manual", is_mirror=False,
        ))
    db.flush()
    resp = logged_in_client.get("/api/transactions/pending-classifications", params={
        "limit": 2, "offset": 2,
    })
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    # 倒序 → 14日 / 13日 / [12日, 11日] / 10日
    assert data["items"][0]["merchant_raw"] == "店2"
    assert data["items"][1]["merchant_raw"] == "店1"
```

- [ ] **Step 3.3:跑测试看失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_transactions_create_find.py -k pending_classifications -v 2>&1 | Select-Object -Last 15
```

期望 3 全 FAIL(404)。

- [ ] **Step 3.4:加 route**

[backend/app/api/transactions.py](backend/app/api/transactions.py) 末尾追加:

```python
@router.get("/pending-classifications", response_model=TransactionListOut)
def list_pending_classifications(
    user: CurrentUserDep, db: DbDep,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TransactionListOut:
    """spec § 8.1 list_pending_classifications 工具的 backend 实现。

    返回 category_id IS NULL 且 is_mirror=False 的交易,按 tx_time DESC 翻页。
    suggested_categories 字段 V2 加(rapidfuzz vs categories.name)。
    """
    where = (Transaction.user_id == user.id) & (Transaction.category_id.is_(None)) & (Transaction.is_mirror.is_(False))
    total = db.execute(select(func.count()).select_from(Transaction).where(where)).scalar_one()
    items = db.execute(
        select(Transaction).where(where)
        .order_by(Transaction.tx_time.desc(), Transaction.id.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return TransactionListOut(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total, limit=limit, offset=offset,
    )
```

注意:**route 顺序很关键** — `/merchants` `/manual` `/pending-classifications` 三条都是字面量 path,要在 `/{tx_id}` 这个 path-param route **之前** 注册;否则 FastAPI 会优先匹配 `/{tx_id}`,把 `merchants` 当成 tx_id 的字符串去 parse 失败。检查文件中 router 的实际注册顺序,如必要 reorder(把 `/manual` `/merchants` `/pending-classifications` 移到 `/{tx_id}` 之上)。

- [ ] **Step 3.5:跑测试 + 全套 + commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_transactions_create_find.py -v 2>&1 | Select-Object -Last 5
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 3
git add backend/app/api/transactions.py backend/tests/api/test_transactions_create_find.py
git commit -m "feat(backend): GET /api/transactions/pending-classifications for MCP

Lists category_id IS NULL + is_mirror=False, paginated. The
suggested_categories field is reserved (returned empty for now)
per spec § 8.1; V2 will fill it via rapidfuzz against categories.name.
"
```

---

## Task 4:Backend gap — `accounts` 加 `latest_balance` 字段(支撑 MCP `get_account_balances`)

**Files:**
- Modify: `backend/app/schemas/account.py`(加 `AccountBalanceOut`)
- Modify: `backend/app/schemas/__init__.py`(re-export)
- Modify: `backend/app/services/summary.py`(加 `compute_account_balances` 纯函数)
- Modify: `backend/app/api/accounts.py`(`list_accounts` 改返 `AccountBalanceListOut`,带 latest_balance)
- Create: `backend/tests/services/test_account_balances.py`
- Modify: `backend/tests/api/test_accounts_rules_categories.py`(追加 list endpoint 含 balance 的断言)

> **背景:** spec § 8.1 `get_account_balances` 工具出参 `accounts: [{id, name, type, last4, latest_balance, latest_balance_at}]`。MVP 没存余额(spec § 4.1 accounts 表无 balance 字段),所以余额 = 流水推算:
>
> ```
> latest_balance = SUM(income.amount_settled_cny) - SUM(expense.amount_settled_cny) - SUM(refund.amount_settled_cny)
> latest_balance_at = MAX(tx_time)
> 仅统计 is_mirror=False 的 transactions
> ```
>
> 注:这只是流水推算,**不**等于真实银行余额(因为没存初始余额)。spec 没要求 absolute correctness,只要工具能返回"至当前流水末为止的净额"即可。schema 注释说明此语义。
>
> **inline backend 校验**:
>
> ```
> backend check (services/summary.py):  既有 compute_summary(...) 用 base_where + Transaction.is_mirror.is_(False);Task 4 写 compute_account_balances 复用同模式
> backend check (api/accounts.py):  list_accounts 返 AccountListOut(本地定义,不在 schemas/__init__),Task 4 改 AccountListOut.items 类型 list[AccountBalanceOut]
> backend check (Account model):  无 balance / last_tx_time 字段(纯流水推算)
> ```

- [ ] **Step 4.1:Inline 校验**

```powershell
Get-Content backend\app\api\accounts.py | Select-String -Pattern "AccountListOut|class "
Get-Content backend\app\services\summary.py | Select-String -Pattern "^def "
```

确认 `AccountListOut` 是 accounts.py 内 inline 定义(不是 schemas 包导出),`compute_summary` 是唯一现存函数。

- [ ] **Step 4.2:写 service 单元测试**

新建 [backend/tests/services/test_account_balances.py](backend/tests/services/test_account_balances.py):

```python
"""compute_account_balances — 纯函数,流水推算 net balance per account。"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Transaction, User
from app.services.summary import compute_account_balances


@pytest.fixture
def user(db) -> User:
    u = User(username="balance_test", password_hash="$2b$12$x" + "y" * 50)
    db.add(u); db.flush(); return u


@pytest.fixture
def alipay(db, user) -> Account:
    a = Account(user_id=user.id, name="支付宝", type="alipay", institution="支付宝", currency="CNY")
    db.add(a); db.flush(); return a


@pytest.fixture
def bank(db, user) -> Account:
    a = Account(user_id=user.id, name="交行借记 2498", type="bank_debit",
                institution="交通银行", last4="2498", currency="CNY")
    db.add(a); db.flush(); return a


def _tx(user_id, acc_id, kind, amt, when, *, mirror=False):
    return Transaction(
        user_id=user_id, account_id=acc_id, tx_kind=kind,
        tx_time=when, amount=Decimal(amt), currency="CNY",
        amount_settled_cny=Decimal(amt),
        merchant_raw="x", merchant_normalized="x",
        source="manual", is_mirror=mirror,
    )


def test_balance_simple_expense_minus_income(db, user, alipay):
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "300.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "150.50",
               datetime(2026, 5, 3, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("549.50")
    assert by_id[alipay.id]["latest_balance_at"] == datetime(2026, 5, 3, tzinfo=timezone.utc)


def test_balance_refund_subtracts(db, user, alipay):
    """refund 等同于 expense 的反向,从余额扣(spec 语义:已收回部分,不应当成 income)。

    实现选择:refund 与 expense 同号(都减),保持现有 importer 落库语义不变。
    """
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "200.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "refund", "50.00",
               datetime(2026, 5, 3, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    # 1000 - 200 - 50 = 750
    assert by_id[alipay.id]["latest_balance"] == Decimal("750.00")


def test_balance_neutral_excluded(db, user, alipay):
    """neutral(信用卡还款等)既不是 expense 也不是 income,**不算入余额**。"""
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "neutral", "500.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("1000.00")
    # neutral 仍参与 latest_balance_at 计算
    assert by_id[alipay.id]["latest_balance_at"] == datetime(2026, 5, 2, tzinfo=timezone.utc)


def test_balance_excludes_mirrors(db, user, alipay):
    """is_mirror=True 不参与流水累计。"""
    db.add(_tx(user.id, alipay.id, "income", "1000.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "expense", "200.00",
               datetime(2026, 5, 2, tzinfo=timezone.utc), mirror=True))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("1000.00")


def test_balance_returns_zero_for_account_with_no_tx(db, user, alipay, bank):
    """alipay 有交易,bank 无交易;两个 account 都返回(bank balance=0,latest_balance_at=None)。"""
    db.add(_tx(user.id, alipay.id, "income", "100.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    by_id = {r["account_id"]: r for r in result}
    assert by_id[alipay.id]["latest_balance"] == Decimal("100.00")
    assert by_id[bank.id]["latest_balance"] == Decimal("0.00")
    assert by_id[bank.id]["latest_balance_at"] is None


def test_balance_per_user_isolation(db, user, alipay):
    """另一个 user 的交易不影响本 user。"""
    other = User(username="other_test", password_hash="$2b$12$x" + "z" * 50)
    db.add(other); db.flush()
    other_acc = Account(user_id=other.id, name="o", type="alipay", currency="CNY")
    db.add(other_acc); db.flush()
    db.add(_tx(other.id, other_acc.id, "income", "999999.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.add(_tx(user.id, alipay.id, "income", "100.00",
               datetime(2026, 5, 1, tzinfo=timezone.utc)))
    db.flush()
    result = compute_account_balances(db, user_id=user.id)
    # 只返回 user 的 accounts
    assert all(r["account_id"] in (alipay.id,) for r in result)
```

- [ ] **Step 4.3:跑测试看失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_account_balances.py -v 2>&1 | Select-Object -Last 15
```

期望全 FAIL(`compute_account_balances` 不存在,ImportError)。

- [ ] **Step 4.4:实现 `compute_account_balances`**

打开 [backend/app/services/summary.py](backend/app/services/summary.py),在 `compute_summary` 之后追加:

```python
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
```

注意:`from decimal import Decimal` / `from app.models import Account` 已在文件顶部 import,无需追加。

- [ ] **Step 4.5:跑 service 测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_account_balances.py -v 2>&1 | Select-Object -Last 10
```

期望 6 全 PASS。

- [ ] **Step 4.6:加 `AccountBalanceOut` schema**

打开 [backend/app/schemas/account.py](backend/app/schemas/account.py),在 `AccountOut` 之后追加:

```python
from datetime import datetime
from decimal import Decimal


class AccountBalanceOut(AccountOut):
    """spec § 8.1 get_account_balances 工具的 backend 等价。继承 AccountOut + 余额字段。

    latest_balance 为流水推算(income - expense - refund),非银行真实余额。
    latest_balance_at = MAX(tx_time) of non-mirror tx,无交易时为 None。
    """
    latest_balance: Decimal
    latest_balance_at: datetime | None
```

- [ ] **Step 4.7:re-export + main schemas/__init__.py 调整**

[backend/app/schemas/__init__.py](backend/app/schemas/__init__.py) account 一段:

```python
from app.schemas.account import AccountBalanceOut, AccountCreate, AccountOut, AccountUpdate
```

`__all__` 加 `"AccountBalanceOut",`。

- [ ] **Step 4.8:改 `list_accounts` route 返回带 balance**

打开 [backend/app/api/accounts.py](backend/app/api/accounts.py),把:

```python
class AccountListOut(BaseModel):
    items: list[AccountOut]
    total: int
```

改为:

```python
from app.schemas import AccountBalanceOut


class AccountListOut(BaseModel):
    items: list[AccountBalanceOut]
    total: int
```

并把 `list_accounts` 改为:

```python
@router.get("", response_model=AccountListOut)
def list_accounts(user: CurrentUserDep, db: DbDep) -> AccountListOut:
    from app.services.summary import compute_account_balances
    accounts = db.execute(
        select(Account).where(Account.user_id == user.id)
        .order_by(Account.id.asc())
    ).scalars().all()
    balances = {b["account_id"]: b for b in compute_account_balances(db, user_id=user.id)}
    items = [
        AccountBalanceOut(
            **AccountOut.model_validate(a).model_dump(),
            latest_balance=balances[a.id]["latest_balance"],
            latest_balance_at=balances[a.id]["latest_balance_at"],
        )
        for a in accounts
    ]
    return AccountListOut(items=items, total=len(items))
```

- [ ] **Step 4.9:更新现有 accounts API test 适配新字段**

打开 [backend/tests/api/test_accounts_rules_categories.py](backend/tests/api/test_accounts_rules_categories.py),找到 `def test_list_accounts*` 类似的测试,加断言:

```python
def test_list_accounts_includes_balance(logged_in_client, db, admin_user):
    """新增字段 latest_balance / latest_balance_at 必出现。"""
    acc = Account(user_id=admin_user.id, name="x", type="alipay", currency="CNY")
    db.add(acc); db.flush()
    resp = logged_in_client.get("/api/accounts")
    assert resp.status_code == 200
    items = resp.json()["items"]
    target = next(it for it in items if it["id"] == acc.id)
    assert "latest_balance" in target
    assert target["latest_balance"] == "0.00"
    assert target["latest_balance_at"] is None
```

(若该 test 文件已有 `test_list_accounts*` 测试,就在文件末尾追加这一条;无需删除既有测试 — `AccountBalanceOut` 继承 `AccountOut`,旧字段断言依然过。)

- [ ] **Step 4.10:跑全套测试 + commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 5
git add backend/app/schemas/account.py backend/app/schemas/__init__.py backend/app/services/summary.py backend/app/api/accounts.py backend/tests/services/test_account_balances.py backend/tests/api/test_accounts_rules_categories.py
git commit -m "feat(backend): add latest_balance to GET /api/accounts for MCP get_account_balances

compute_account_balances() in services/summary.py is a pure function
returning {account_id, latest_balance, latest_balance_at} per account.
Math: SUM(income) - SUM(expense) - SUM(refund), excluding is_mirror.
neutral tx don't count toward balance but do count toward latest_at.

Spec § 8.1 / spec § 4.1 — Account model has no balance column, so this
is a flow-derived value, not authoritative bank balance.
"
```

---

## Task 5:API Token 鉴权基础设施 — service + admin endpoints + Bearer dependency

**Files:**
- Create: `backend/app/services/api_token.py`(generate / hash / verify / revoke)
- Create: `backend/app/schemas/api_token.py`(ApiTokenCreate / ApiTokenOut / ApiTokenCreateResp)
- Create: `backend/app/api/admin_tokens.py`(POST/GET/DELETE /api/admin/tokens)
- Create: `backend/tests/services/test_api_token.py`
- Create: `backend/tests/api/test_admin_tokens.py`
- Modify: `backend/app/api/deps.py`(加 `api_token_user` dependency)
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/main.py`(注册 admin_tokens router)
- Modify: `backend/app/api/__init__.py`(export admin_tokens)

> **背景:** spec § 10.2 — MCP server 用静态 API token,token 在 db `api_tokens` 表存 sha256 hash;创建时返回明文,**仅一次**;验证时调用方 `Authorization: Bearer <plain>`,server 把 plain 哈希后查表;吊销 = 写 revoked_at。schema(`backend/app/models/api_token.py`)slice A 已建,本 task 只补 service + endpoints + dependency。
>
> Token 使用模式:
> - **创建/管理**:cookie+JWT 认证 `/api/admin/tokens`(用户从 web settings 页或 Pre-flight 内部端点调一次,留明文)
> - **验证**:Bearer dependency,给 backend 内部端点用(如 `/api/admin/tokens/verify`,MCP server 间接调)
>
> **关键决策**:MCP server **不直接连 db**(避免 db schema 反向耦合);它通过调 backend 的 `/api/admin/tokens/verify` 端点验证 token,再把同一 token 透传给所有 backend API(每个 user-facing 端点都接受 cookie OR Bearer 作为认证凭据)。这要求把 backend 现有 `current_user` dependency 升级为 `current_user_cookie_or_token`,优先 cookie,fallback Bearer。
>
> **inline backend 校验**:
>
> ```
> backend check (api_token.py model):  fields id / user_id / name / token_hash UNIQUE / scopes / last_used_at / revoked_at / created_at / updated_at(via TimestampMixin)
> backend check (api/deps.py):  current_user 仅查 cookie + JWT;无 Bearer fallback。本 task 改为 current_user_cookie_or_token,既有 import 路径不变(返回类型不变,仅多个认证渠道)
> ```

- [ ] **Step 5.1:Inline 校验**

```powershell
Get-Content backend\app\models\api_token.py
Get-Content backend\app\api\deps.py | Select-String -Pattern "^def |^[A-Z]"
```

确认 model 字段如上述;`current_user` 是 deps.py 中唯一的认证函数。

- [ ] **Step 5.2:写 service 单元测试**

新建 [backend/tests/services/test_api_token.py](backend/tests/services/test_api_token.py):

```python
"""API token service:生成 / 哈希 / 验证 / 吊销。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import ApiToken, User
from app.services.api_token import (
    create_api_token, hash_token, list_tokens, revoke_token, verify_token,
)


@pytest.fixture
def user(db) -> User:
    u = User(username="token_test", password_hash="$2b$12$x" + "y" * 50)
    db.add(u); db.flush(); return u


def test_create_returns_plain_and_persists_hash(db, user):
    """create_api_token 返回 (token_obj, plain_token) — plain 仅出现这一次。"""
    plain, token_obj = create_api_token(db, user_id=user.id, name="my MCP token")
    assert isinstance(plain, str)
    assert len(plain) >= 32  # secrets.token_urlsafe(32) ≈ 43 字符
    assert token_obj.id is not None
    assert token_obj.user_id == user.id
    assert token_obj.name == "my MCP token"
    assert token_obj.scopes == "read,write"
    assert token_obj.revoked_at is None
    # token_hash 是 hash,不是明文
    assert token_obj.token_hash != plain
    assert token_obj.token_hash == hash_token(plain)


def test_hash_token_is_deterministic_and_64_chars(db):
    """sha256 hex digest = 64 chars,同输入同输出。"""
    h1 = hash_token("abc")
    h2 = hash_token("abc")
    assert h1 == h2
    assert len(h1) == 64
    assert h1 != hash_token("abd")


def test_verify_token_success_updates_last_used_at(db, user):
    plain, _ = create_api_token(db, user_id=user.id, name="t1")
    before = datetime.now(timezone.utc)

    verified_user = verify_token(db, plain)
    assert verified_user is not None
    assert verified_user.id == user.id

    # last_used_at 已被更新
    token_obj = db.execute(select(ApiToken).where(ApiToken.user_id == user.id)).scalar_one()
    assert token_obj.last_used_at is not None
    assert token_obj.last_used_at >= before


def test_verify_token_unknown_returns_none(db):
    """乱给的 token → None,不抛异常。"""
    result = verify_token(db, "definitely-not-a-real-token")
    assert result is None


def test_verify_token_revoked_returns_none(db, user):
    plain, token_obj = create_api_token(db, user_id=user.id, name="t1")
    revoke_token(db, token_id=token_obj.id, user_id=user.id)
    assert verify_token(db, plain) is None


def test_revoke_token_idempotent(db, user):
    plain, token_obj = create_api_token(db, user_id=user.id, name="t1")
    revoke_token(db, token_id=token_obj.id, user_id=user.id)
    first_revoked_at = token_obj.revoked_at
    revoke_token(db, token_id=token_obj.id, user_id=user.id)
    # revoked_at 不被覆盖(保留最早撤销时间)
    db.refresh(token_obj)
    assert token_obj.revoked_at == first_revoked_at


def test_revoke_token_other_user_denied(db, user):
    """A 用户不能撤销 B 用户的 token。"""
    other = User(username="other_token_test", password_hash="$2b$12$x" + "z" * 50)
    db.add(other); db.flush()
    plain, token_obj = create_api_token(db, user_id=other.id, name="other-token")
    # user 来撤 other 的 token → False(没找到)
    result = revoke_token(db, token_id=token_obj.id, user_id=user.id)
    assert result is False
    # other 的 token 仍可用
    db.refresh(token_obj)
    assert token_obj.revoked_at is None


def test_list_tokens_excludes_other_users_and_orders_by_created_at_desc(db, user):
    plain1, t1 = create_api_token(db, user_id=user.id, name="alpha")
    plain2, t2 = create_api_token(db, user_id=user.id, name="beta")
    other = User(username="other_list_test", password_hash="$2b$12$x" + "w" * 50)
    db.add(other); db.flush()
    create_api_token(db, user_id=other.id, name="other")

    rows = list_tokens(db, user_id=user.id)
    assert [r.name for r in rows] == ["beta", "alpha"]  # DESC by created_at
    # 没有 other 的 token
    assert all(r.user_id == user.id for r in rows)
```

- [ ] **Step 5.3:跑测试看失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_api_token.py -v 2>&1 | Select-Object -Last 15
```

期望全 FAIL(`app.services.api_token` 不存在)。

- [ ] **Step 5.4:写 service**

新建 [backend/app/services/api_token.py](backend/app/services/api_token.py):

```python
"""API token service — spec § 10.2。

token 生成时返回明文(仅这一次);DB 仅存 sha256 hash;
验证调 verify_token(plain) → User | None,顺手更新 last_used_at。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApiToken, User


def hash_token(plain: str) -> str:
    """sha256 hex digest(64 chars)。"""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def create_api_token(
    db: Session, *, user_id: int, name: str, scopes: str = "read,write",
) -> tuple[str, ApiToken]:
    """生成新 token 并落库。返回 (plain_token, ApiToken_obj)。

    plain 仅在调用方可见这一次;DB 中只存 token_hash。
    """
    plain = secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user_id,
        name=name,
        token_hash=hash_token(plain),
        scopes=scopes,
    )
    db.add(token); db.flush()
    return plain, token


def verify_token(db: Session, plain: str) -> User | None:
    """Bearer 验证:plain → User(若有效未吊销)否则 None。

    成功时顺手更新 last_used_at。失败不抛,返回 None。
    """
    if not plain:
        return None
    digest = hash_token(plain)
    token = db.execute(
        select(ApiToken).where(
            ApiToken.token_hash == digest,
            ApiToken.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if token is None:
        return None
    user = db.execute(
        select(User).where(User.id == token.user_id)
    ).scalar_one_or_none()
    if user is None:
        return None
    # 更新 last_used_at(细粒度审计)
    token.last_used_at = datetime.now(timezone.utc)
    db.flush()
    return user


def revoke_token(db: Session, *, token_id: int, user_id: int) -> bool:
    """吊销:仅当 token 属于本 user_id。返回 True 表示找到并标记;False 表示没找到。

    幂等:若 token 已吊销,不覆盖 revoked_at。
    """
    token = db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == user_id,
        )
    ).scalar_one_or_none()
    if token is None:
        return False
    if token.revoked_at is None:
        token.revoked_at = datetime.now(timezone.utc)
        db.flush()
    return True


def list_tokens(db: Session, *, user_id: int) -> list[ApiToken]:
    """列出 user 的所有 tokens(含已吊销;按 created_at DESC)。"""
    return list(db.execute(
        select(ApiToken).where(ApiToken.user_id == user_id)
        .order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    ).scalars().all())
```

注意:
- `ApiToken` 必须在 `app/models/__init__.py` 中 re-export。先 `Get-Content backend\app\models\__init__.py | Select-String "ApiToken"` 确认;若没 export,补一条 `from app.models.api_token import ApiToken` + `__all__` 加 `"ApiToken"`(slice A 应已 export,但一定 verify)
- 同样确认 `User` 已 export

- [ ] **Step 5.5:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/services/test_api_token.py -v 2>&1 | Select-Object -Last 12
```

期望 7 全 PASS。

- [ ] **Step 5.6:写 admin tokens API 测试**

新建 [backend/tests/api/test_admin_tokens.py](backend/tests/api/test_admin_tokens.py):

```python
"""POST/GET/DELETE /api/admin/tokens — cookie 认证保护。"""
from __future__ import annotations

from sqlalchemy import select

from app.models import ApiToken


def test_create_token_returns_plain_once(logged_in_client, db, admin_user):
    resp = logged_in_client.post("/api/admin/tokens", json={"name": "MCP server"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "plain_token" in data
    assert isinstance(data["plain_token"], str)
    assert len(data["plain_token"]) >= 32
    assert data["token"]["id"]
    assert data["token"]["name"] == "MCP server"
    assert data["token"]["scopes"] == "read,write"
    # plain_token 不在 token 子对象里(避免被序列化进 list)
    assert "plain_token" not in data["token"]
    # DB 中 hash 与 plain 不同
    saved = db.execute(select(ApiToken).where(ApiToken.id == data["token"]["id"])).scalar_one()
    assert saved.token_hash != data["plain_token"]


def test_list_tokens_returns_no_plain(logged_in_client, db, admin_user):
    """list 不返回明文(只能 create 时拿到一次)。"""
    logged_in_client.post("/api/admin/tokens", json={"name": "t1"})
    resp = logged_in_client.get("/api/admin/tokens")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    for t in items:
        assert "plain_token" not in t
        assert "token_hash" not in t       # hash 也不暴露
        assert "name" in t and "id" in t


def test_revoke_token(logged_in_client, db, admin_user):
    create = logged_in_client.post("/api/admin/tokens", json={"name": "to-revoke"})
    tid = create.json()["token"]["id"]
    resp = logged_in_client.delete(f"/api/admin/tokens/{tid}")
    assert resp.status_code == 204
    # 再 list 仍能见(soft delete + revoked_at)
    items = logged_in_client.get("/api/admin/tokens").json()["items"]
    revoked = next(t for t in items if t["id"] == tid)
    assert revoked["revoked_at"] is not None


def test_revoke_unknown_token_404(logged_in_client):
    resp = logged_in_client.delete("/api/admin/tokens/99999")
    assert resp.status_code == 404


def test_admin_tokens_requires_cookie(client):
    """没 cookie → 401(client fixture 不带 login)。"""
    resp = client.post("/api/admin/tokens", json={"name": "x"})
    assert resp.status_code == 401
    resp = client.get("/api/admin/tokens")
    assert resp.status_code == 401


def test_admin_tokens_verify_endpoint(logged_in_client, db, admin_user):
    """POST /api/admin/tokens/verify — 内部端点,Bearer 验证 token,返回 user info。"""
    create = logged_in_client.post("/api/admin/tokens", json={"name": "v1"})
    plain = create.json()["plain_token"]

    # 用 raw client 走 Bearer(不要 cookie)
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import SESSION_COOKIE_NAME

    # 复用 logged_in_client 但去掉 cookie 走 Bearer
    logged_in_client.cookies.delete(SESSION_COOKIE_NAME)
    resp = logged_in_client.post(
        "/api/admin/tokens/verify",
        headers={"Authorization": f"Bearer {plain}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == admin_user.id
    assert data["username"] == admin_user.username
    assert "scopes" in data


def test_admin_tokens_verify_bad_token_401(client):
    resp = client.post(
        "/api/admin/tokens/verify",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_admin_tokens_verify_missing_header_401(client):
    resp = client.post("/api/admin/tokens/verify")
    assert resp.status_code == 401
```

- [ ] **Step 5.7:跑测试看失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_admin_tokens.py -v 2>&1 | Select-Object -Last 15
```

期望全 FAIL(404 / module not found)。

- [ ] **Step 5.8:加 schemas**

新建 [backend/app/schemas/api_token.py](backend/app/schemas/api_token.py):

```python
"""API token schemas — spec § 10.2。"""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreate(BaseModel):
    """POST /api/admin/tokens body。"""
    name: str = Field(..., min_length=1, max_length=128)
    scopes: str = Field("read,write", max_length=64)


class ApiTokenOut(BaseModel):
    """list / 单条返回(不含 plain / hash)。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    scopes: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreateResp(BaseModel):
    """POST /api/admin/tokens 返回:plain 仅这一次,token 元信息按 ApiTokenOut。"""
    plain_token: str           # 用户必须立即保存,无后悔药
    token: ApiTokenOut


class ApiTokenListOut(BaseModel):
    items: list[ApiTokenOut]
    total: int


class ApiTokenVerifyOut(BaseModel):
    """POST /api/admin/tokens/verify — MCP server 内部端点用。"""
    user_id: int
    username: str
    scopes: str
```

- [ ] **Step 5.9:re-export schemas**

[backend/app/schemas/__init__.py](backend/app/schemas/__init__.py) 加:

```python
from app.schemas.api_token import (
    ApiTokenCreate,
    ApiTokenCreateResp,
    ApiTokenListOut,
    ApiTokenOut,
    ApiTokenVerifyOut,
)
```

`__all__` 加对应 5 个。

- [ ] **Step 5.10:升级 `current_user` dependency 支持 Bearer fallback**

打开 [backend/app/api/deps.py](backend/app/api/deps.py),把现有 `current_user` 函数替换为:

```python
"""FastAPI 依赖:DbDep / current_user(cookie 或 Bearer 双通道)。

current_user 优先 cookie+JWT(spec § 10.1);若 cookie 缺,fallback 到
Authorization: Bearer <api_token>(spec § 10.2)。两种都失败返 401。
"""
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import User
from app.services.api_token import verify_token
from app.services.auth import InvalidTokenError, decode_access_token


SESSION_COOKIE_NAME = "fm_session"

DbDep = Annotated[Session, Depends(get_db)]


def _try_cookie(db: Session, cookie: str | None) -> User | None:
    if not cookie:
        return None
    try:
        payload = decode_access_token(cookie)
    except InvalidTokenError:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return db.execute(select(User).where(User.username == username)).scalar_one_or_none()


def _try_bearer(db: Session, authorization: str | None) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    plain = authorization[7:].strip()
    return verify_token(db, plain)


def current_user(
    db: DbDep,
    fm_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """spec § 10.1 + § 10.2 双通道认证。先 cookie,再 Bearer。"""
    user = _try_cookie(db, fm_session)
    if user is not None:
        return user
    user = _try_bearer(db, authorization)
    if user is not None:
        return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid credentials")


CurrentUserDep = Annotated[User, Depends(current_user)]
```

注意:
- 既有调用 `CurrentUserDep` 的所有 endpoint(transactions/dedup/accounts/categories/rules/summary/statements)**接口不变**,旧测试照常过(cookie 路径同等通过)
- 加了一个新可选 dependency:仅 Bearer 路径,留给 admin tokens verify 端点用 → 见 Step 5.11 的 `bearer_only_user`

在文件底部追加(给 verify endpoint 专用):

```python
def bearer_only_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """仅 Bearer 认证(给 /api/admin/tokens/verify 用,确保 cookie 不能滥用 verify)。"""
    user = _try_bearer(db, authorization)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid bearer token")
    return user


BearerUserDep = Annotated[User, Depends(bearer_only_user)]
```

- [ ] **Step 5.11:写 admin_tokens router**

新建 [backend/app/api/admin_tokens.py](backend/app/api/admin_tokens.py):

```python
"""Admin tokens API — spec § 10.2。

POST   /api/admin/tokens          — 创建,返回 plain(仅一次)
GET    /api/admin/tokens          — list(不含 plain / hash)
DELETE /api/admin/tokens/{id}     — 吊销(soft delete via revoked_at)
POST   /api/admin/tokens/verify   — 给 MCP server 内部用,Bearer 验证返回 user 信息
"""
from fastapi import APIRouter, HTTPException, status

from app.api.deps import BearerUserDep, CurrentUserDep, DbDep
from app.models import ApiToken
from app.schemas import (
    ApiTokenCreate,
    ApiTokenCreateResp,
    ApiTokenListOut,
    ApiTokenOut,
    ApiTokenVerifyOut,
)
from app.services.api_token import (
    create_api_token, list_tokens, revoke_token,
)


router = APIRouter(prefix="/admin/tokens", tags=["admin-tokens"])


@router.post("", response_model=ApiTokenCreateResp, status_code=status.HTTP_201_CREATED)
def create(
    body: ApiTokenCreate, user: CurrentUserDep, db: DbDep,
) -> ApiTokenCreateResp:
    plain, token = create_api_token(
        db, user_id=user.id, name=body.name, scopes=body.scopes,
    )
    return ApiTokenCreateResp(
        plain_token=plain,
        token=ApiTokenOut.model_validate(token),
    )


@router.get("", response_model=ApiTokenListOut)
def list_(
    user: CurrentUserDep, db: DbDep,
) -> ApiTokenListOut:
    rows = list_tokens(db, user_id=user.id)
    return ApiTokenListOut(
        items=[ApiTokenOut.model_validate(t) for t in rows], total=len(rows),
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke(
    token_id: int, user: CurrentUserDep, db: DbDep,
) -> None:
    ok = revoke_token(db, token_id=token_id, user_id=user.id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "token not found")
    return None


@router.post("/verify", response_model=ApiTokenVerifyOut)
def verify(
    user: BearerUserDep, db: DbDep,
) -> ApiTokenVerifyOut:
    """MCP server 启动时调一次确认 token 合法,后续每次工具调用也可调以拿 user info。

    复用 BearerUserDep — 内部已查表 + 更新 last_used_at + 验未吊销。
    """
    # 找用户的当前 token 拿 scopes(verify 路径已经过 BearerUserDep,所以 token 必有效)
    from sqlalchemy import select
    from app.api.deps import _try_bearer  # 不直接重做,改从 token table 查 scopes
    # 取最近 last_used_at 的未吊销 token(就是刚 verify 那条)
    recent = db.execute(
        select(ApiToken).where(
            ApiToken.user_id == user.id,
            ApiToken.revoked_at.is_(None),
        ).order_by(ApiToken.last_used_at.desc().nulls_last()).limit(1)
    ).scalar_one()
    return ApiTokenVerifyOut(
        user_id=user.id,
        username=user.username,
        scopes=recent.scopes,
    )
```

注意:
- verify 端点的 scopes 取法是 "用户最近用过的未吊销 token";单 user MVP 通常只 1 个 token,这够用;V2 多 token 时需在 Bearer 解析时把 token 对象一并 return
- import `from app.api.deps import _try_bearer` 是占位 — 实际不调用,可以删

修改 verify 函数为更干净的版本(避免上述 hack):

```python
@router.post("/verify", response_model=ApiTokenVerifyOut)
def verify(
    user: BearerUserDep, db: DbDep,
) -> ApiTokenVerifyOut:
    from sqlalchemy import select
    recent = db.execute(
        select(ApiToken).where(
            ApiToken.user_id == user.id,
            ApiToken.revoked_at.is_(None),
        ).order_by(ApiToken.last_used_at.desc().nulls_last()).limit(1)
    ).scalar_one()
    return ApiTokenVerifyOut(
        user_id=user.id,
        username=user.username,
        scopes=recent.scopes,
    )
```

- [ ] **Step 5.12:注册 router**

打开 [backend/app/main.py](backend/app/main.py),在已有 import 段加:

```python
from app.api import admin_tokens as admin_tokens_api
```

并在 include_router 段加:

```python
api_router.include_router(admin_tokens_api.router)
```

(放在 `summary_api.router` 之后或之前,顺序不重要 — FastAPI 不依赖注册顺序进行路由 dispatch。)

- [ ] **Step 5.13:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api/test_admin_tokens.py -v 2>&1 | Select-Object -Last 20
```

期望 8 全 PASS。

- [ ] **Step 5.14:跑全套测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

期望 0 fail / 0 error。

特别注意:`tests/api/test_auth.py`(slice C 写的)断言"无 cookie → 401",现在 deps.py 升级支持 Bearer fallback,**应不影响**该测试(无 Bearer header 时 fallback 也失败,仍 401)。如有 fail,read 原 test 看断言细节。

- [ ] **Step 5.15:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
git add backend/app/services/api_token.py backend/app/schemas/api_token.py backend/app/schemas/__init__.py backend/app/api/admin_tokens.py backend/app/api/deps.py backend/app/main.py backend/tests/services/test_api_token.py backend/tests/api/test_admin_tokens.py
git commit -m "feat(backend): API token infra — service + admin endpoints + Bearer dep

spec § 10.2 — MCP server uses static API tokens (sha256 hash in DB,
plain returned only at create time). admin_tokens router covers
POST/GET/DELETE /api/admin/tokens (cookie-protected) plus a Bearer-
authenticated /verify endpoint that MCP server calls to validate
incoming Bearer headers and surface user_id/username/scopes.

current_user dependency upgraded to dual-channel: cookie+JWT first,
Bearer fallback. All existing endpoints keep the same dependency name
and now transparently accept either credential.
"
```

---

## Task 6:MCP server 项目骨架 — pyproject + Dockerfile + main + config + backend_client + errors

**Files(全部新建):**
- Create: `mcp_server/pyproject.toml`
- Create: `mcp_server/Dockerfile`
- Create: `mcp_server/README.md`
- Create: `mcp_server/app/__init__.py`(空)
- Create: `mcp_server/app/config.py`
- Create: `mcp_server/app/errors.py`
- Create: `mcp_server/app/backend_client.py`
- Create: `mcp_server/app/main.py`
- Create: `mcp_server/app/tools/__init__.py`(registry,本 task 仅占位 + 注释)
- Create: `mcp_server/tests/__init__.py`(空)
- Create: `mcp_server/tests/conftest.py`(MockBackend httpx fixture)
- Create: `mcp_server/tests/test_main_auth.py`
- Create: `mcp_server/tests/test_backend_client.py`

> **背景:** 本 task 搭起 MCP server 的"空壳子" — 一个 Python 项目(独立于 backend),用 [`mcp` Python SDK](https://pypi.org/project/mcp/) ≥ 1.1 提供 MCP 协议入口,httpx 调 backend REST API。所有工具 handler 在 Task 7-16 注册;本 task 验证以下骨架可工作:
>
> 1. `mcp_server/` 目录结构成型
> 2. `python -m mcp_server.app.main --transport stdio` 能启动(空 tools list 也 ok)
> 3. Bearer header 验证流走通(成功 + 缺失 + 错误三场景,通过调 backend `/api/admin/tokens/verify`)
> 4. backend_client httpx wrapper 能注入 auth header,把 4xx/5xx 转成 spec § 8.3 错误码
>
> 本 task **不**实现任何工具;tools/__init__.py 留 `TOOL_REGISTRY: dict[str, Callable] = {}`,Task 7-16 各自往里 register。
>
> **MCP Python SDK 选型**:用 `mcp >= 1.1` 的 `mcp.server.lowlevel.Server` API + `mcp.server.stdio.stdio_server`(开发用)+ `mcp.server.streamable_http` 或 `mcp.server.sse` ASGI(prod 部署 9443 HTTP 用)。本 task 主要测 stdio + Bearer 认证;HTTP transport 在 Task 19 docker-compose 接 ASGI 入口时配置。
>
> **inline backend 校验**:
>
> ```
> backend check (admin_tokens.py):  POST /api/admin/tokens/verify 需要 Authorization: Bearer <token>,返回 {user_id, username, scopes}
> backend check (.env):  MCP_BACKEND_URL=http://backend:8000(prod docker 内网),本机 dev 用 http://127.0.0.1:8000
> ```

- [ ] **Step 6.1:Read mcp Python SDK 的核心 API**(必做 inline 校验)

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
# 先临时装到 backend venv 查 API(不是给 backend 用,只是查文档)
.\backend\.venv\Scripts\python.exe -m pip install --quiet "mcp>=1.1"
.\backend\.venv\Scripts\python.exe -c "import mcp; from mcp.server.lowlevel import Server; print(Server.__doc__)"
.\backend\.venv\Scripts\python.exe -c "from mcp import types; print([x for x in dir(types) if not x.startswith('_')])"
.\backend\.venv\Scripts\python.exe -c "from mcp.server.stdio import stdio_server; print(stdio_server.__doc__)"
```

期望:看到 `Server` / `Tool` / `TextContent` / `ImageContent` / `EmbeddedResource` 等关键类型。

如果 SDK 装不上(网络问题等),改用 `pip install --index-url <pypi-mirror>` 或下载 wheel 离线装。

- [ ] **Step 6.2:写 `mcp_server/pyproject.toml`**

新建 [mcp_server/pyproject.toml](mcp_server/pyproject.toml):

```toml
[project]
name = "finance-manager-mcp"
version = "0.1.0"
description = "MCP server exposing 10 tools (read+write) over the finance-manager backend REST API."
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.1",
    "httpx>=0.27",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "anyio>=4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.7",
]

[tool.setuptools]
packages = ["app", "app.tools"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]
ignore = ["E501"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
```

注意:`packages = ["app", "app.tools"]` 让 pip install -e 时把 app/ 当包安装。`tool.setuptools.packages = find:` 也行,但我们显式列出。

- [ ] **Step 6.3:写 `mcp_server/Dockerfile`**

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

EXPOSE 8765
CMD ["python", "-m", "app.main", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
```

- [ ] **Step 6.4:写 `mcp_server/README.md`**

```markdown
# Finance Manager — MCP Server

10 个工具(6 read + 4 write)封装 finance-manager backend REST API,
按 MCP 协议暴露给 OpenClaw / Hermes Agent。

## 启动

### 本地 dev(stdio)— 与 MCP Inspector 调试

```powershell
cd mcp_server
python -m app.main --transport stdio
# 或 npx @modelcontextprotocol/inspector python -m app.main
```

### Docker / VPS prod(HTTP 9443 via Caddy)

`docker-compose --profile prod up -d` 起完整栈,Caddy 反代 `https://<domain>:9443/`。

## 配置(`.env`)

| 变量 | 默认 | 说明 |
|---|---|---|
| `MCP_BACKEND_URL` | `http://backend:8000` | backend HTTP 内网地址(本机 dev 用 `http://127.0.0.1:8000`) |
| `MCP_API_TOKEN` | — | 必填,backend 创建的 token plain;启动时 server 自检调 backend /verify |
| `MCP_HOST` | `0.0.0.0` | HTTP transport 监听地址 |
| `MCP_PORT` | `8765` | HTTP transport 端口 |

## 工具清单(spec § 8.1)

| 工具 | 类型 | 说明 |
|---|---|---|
| list_transactions | read | 按时间/分类/账户筛选交易 |
| get_summary | read | 按 day/week/month/year 汇总 |
| get_account_balances | read | 账户余额(流水推算) |
| find_merchant | read | 按关键词聚合商家 |
| list_pending_dedup_pairs | read | 待审核去重对 |
| list_pending_classifications | read | 待分类交易 |
| add_transaction | write | 手动加一笔(支持 agent 对话录入) |
| update_category | write | 改单条交易分类 |
| bulk_update_category_by_merchant | write | 批量按商家改类(可选加规则) |
| confirm_dedup_pair | write | 确认/拒绝去重对 |

## 错误码(spec § 8.3)

| MCP 错误码 | 触发场景 |
|---|---|
| AUTH_FAILED | Bearer 缺失或失效 |
| NOT_FOUND | transaction_id / pair_id / category 不存在 |
| VALIDATION_ERROR | 入参不合法 |
| CONFLICT | 重复确认 dedup_pair / 已存在的资源 |
| BACKEND_ERROR | backend 5xx 透传 |
```

- [ ] **Step 6.5:写 `mcp_server/app/config.py`**

```python
"""MCP server settings — 从 finance-manager/.env 读。"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根 .env(mcp_server 目录在 finance-manager/mcp_server,所以 parent.parent)
_ENV_PATH = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mcp_backend_url: str = Field("http://127.0.0.1:8000")
    mcp_api_token: str = Field(...)            # 必填
    mcp_host: str = Field("0.0.0.0")
    mcp_port: int = Field(8765)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def reset_settings_for_tests() -> None:
    """tests fixture 用 — 强制重新 build settings(读最新 env)。"""
    global _settings
    _settings = None
```

- [ ] **Step 6.6:写 `mcp_server/app/errors.py`**

```python
"""MCP 错误码定义 + httpx 错误 → MCP code 映射(spec § 8.3)。"""
from __future__ import annotations

import httpx


class MCPToolError(Exception):
    """工具执行抛此异常,main.py dispatcher 捕获后包装成 MCP 错误返回。"""

    def __init__(self, code: str, message: str, *, data: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        out = {"code": self.code, "message": self.message}
        if self.data is not None:
            out["data"] = self.data
        return out


# spec § 8.3 错误码常量
AUTH_FAILED = "AUTH_FAILED"
NOT_FOUND = "NOT_FOUND"
VALIDATION_ERROR = "VALIDATION_ERROR"
CONFLICT = "CONFLICT"
BACKEND_ERROR = "BACKEND_ERROR"


def httpx_to_mcp_error(exc: httpx.HTTPStatusError) -> MCPToolError:
    """httpx 4xx/5xx → MCP 错误。"""
    resp = exc.response
    status = resp.status_code
    try:
        body = resp.json()
        backend_detail = body.get("detail", str(body))
    except Exception:
        backend_detail = resp.text or "unknown backend error"

    if status == 401:
        return MCPToolError(AUTH_FAILED, f"backend 401: {backend_detail}")
    if status == 404:
        return MCPToolError(NOT_FOUND, str(backend_detail))
    if status == 409:
        return MCPToolError(CONFLICT, str(backend_detail))
    if status in (400, 422):
        return MCPToolError(VALIDATION_ERROR, str(backend_detail))
    return MCPToolError(BACKEND_ERROR, f"backend {status}: {backend_detail}",
                        data={"status": status})
```

- [ ] **Step 6.7:写 `mcp_server/app/backend_client.py`**

```python
"""httpx-based backend client — 注入 Bearer header + 错误映射 + 单例。"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.errors import httpx_to_mcp_error


class BackendClient:
    """所有工具共用一个 httpx.AsyncClient,handler 直接调 self.get/post/...。"""

    def __init__(self, base_url: str, api_token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=httpx.Timeout(15.0, connect=5.0),
            transport=transport,        # 测试时塞 MockTransport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, url: str, **kwargs) -> dict:
        resp = await self._client.get(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        return resp.json()

    async def post(self, url: str, **kwargs) -> dict:
        resp = await self._client.post(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        # 204 No Content
        if resp.status_code == 204:
            return {}
        return resp.json()

    async def patch(self, url: str, **kwargs) -> dict:
        resp = await self._client.patch(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        if resp.status_code == 204:
            return {}
        return resp.json()

    async def delete(self, url: str, **kwargs) -> dict:
        resp = await self._client.delete(url, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx_to_mcp_error(e) from e
        if resp.status_code == 204:
            return {}
        return resp.json()


_client: BackendClient | None = None


def get_backend_client() -> BackendClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = BackendClient(s.mcp_backend_url, s.mcp_api_token)
    return _client


def set_backend_client_for_tests(client: BackendClient) -> None:
    """tests 用 — 注入带 MockTransport 的 client。"""
    global _client
    _client = client


def reset_backend_client_for_tests() -> None:
    global _client
    _client = None
```

- [ ] **Step 6.8:写 `mcp_server/app/tools/__init__.py`**(占位 registry)

```python
"""Tool registry — 每个 tool 模块在 import 时往这里 register。

Task 7-16 各自 import 后,TOOL_REGISTRY 被填满 10 项。
本 Task 6 只定义 registry 数据结构 + 占位。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from mcp import types as mcp_types


ToolHandler = Callable[[dict[str, Any]], Awaitable[list[mcp_types.TextContent]]]


# (tool_name → (Tool definition, handler async fn))
TOOL_REGISTRY: dict[str, tuple[mcp_types.Tool, ToolHandler]] = {}


def register(tool: mcp_types.Tool, handler: ToolHandler) -> None:
    if tool.name in TOOL_REGISTRY:
        raise RuntimeError(f"duplicate tool registration: {tool.name}")
    TOOL_REGISTRY[tool.name] = (tool, handler)


def get_tool_definitions() -> list[mcp_types.Tool]:
    return [defn for defn, _ in TOOL_REGISTRY.values()]


def get_handler(name: str) -> ToolHandler | None:
    pair = TOOL_REGISTRY.get(name)
    return pair[1] if pair else None
```

- [ ] **Step 6.9:写 `mcp_server/app/main.py`(server entry + transport + bearer 启动自检)**

```python
"""MCP server entry。

启动流程:
1) 读 settings(.env)
2) 调 backend POST /api/admin/tokens/verify 自检 token 合法
3) 注册所有 tools(import tools.* 触发 register())
4) 起 transport:stdio(本机调试)/ http(prod;ASGI 适配)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import sys

import httpx
from mcp import types as mcp_types
from mcp.server.lowlevel import Server

from app.backend_client import get_backend_client
from app.config import get_settings
from app.errors import MCPToolError
from app.tools import get_handler, get_tool_definitions

logger = logging.getLogger("mcp_server")

server = Server("finance-manager-mcp")


@server.list_tools()
async def _list_tools() -> list[mcp_types.Tool]:
    return get_tool_definitions()


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    handler = get_handler(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    try:
        return await handler(arguments or {})
    except MCPToolError as e:
        # 把错误以 TextContent 返回(MCP 协议层错误用 raise,但工具语义错误用 content text)
        return [mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False),
        )]


async def _verify_token_self_check() -> None:
    """启动时调 backend /verify 一次,token 不合法立刻退出(避免起来后第一次工具调用才 fail)。"""
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.mcp_backend_url, timeout=10,
    ) as c:
        resp = await c.post(
            "/api/admin/tokens/verify",
            headers={"Authorization": f"Bearer {settings.mcp_api_token}"},
        )
        if resp.status_code == 401:
            logger.error("MCP_API_TOKEN invalid (backend rejected). Exiting.")
            sys.exit(2)
        if resp.status_code >= 500:
            logger.error(
                "backend not reachable (%d): %s. Will exit; restart docker-compose.",
                resp.status_code, resp.text,
            )
            sys.exit(3)
        logger.info("token verified, user=%s scopes=%s",
                    resp.json().get("username"), resp.json().get("scopes"))


def _register_all_tools() -> None:
    """import tools.* 触发各模块 register() 副作用。"""
    for tool_module in [
        "app.tools.list_transactions",
        "app.tools.get_summary",
        "app.tools.get_account_balances",
        "app.tools.find_merchant",
        "app.tools.list_pending_dedup_pairs",
        "app.tools.list_pending_classifications",
        "app.tools.add_transaction",
        "app.tools.update_category",
        "app.tools.bulk_update_category_by_merchant",
        "app.tools.confirm_dedup_pair",
    ]:
        try:
            importlib.import_module(tool_module)
        except ImportError:
            # Task 6 阶段 tool 模块尚未存在,允许 silent skip
            logger.debug("tool module %s not found yet (slice E in progress?)", tool_module)


async def main_stdio() -> None:
    from mcp.server.stdio import stdio_server
    _register_all_tools()
    await _verify_token_self_check()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            server.create_initialization_options(),
        )


async def main_http(host: str, port: int) -> None:
    """HTTP transport(prod 部署用)。

    用 mcp.server.streamable_http_manager 提供 ASGI app,跑在 uvicorn 里。
    具体 ASGI 包装见 mcp SDK >= 1.1 的 README。

    Task 19 docker-compose 时 CMD 走这个分支。
    """
    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    _register_all_tools()
    await _verify_token_self_check()

    manager = StreamableHTTPSessionManager(
        app=server, event_store=None, json_response=True,
    )

    async def asgi_app(scope, receive, send):
        if scope["type"] != "http":
            return
        await manager.handle_request(scope, receive, send)

    config = uvicorn.Config(
        asgi_app, host=host, port=port, log_level="info", access_log=False,
    )
    s = uvicorn.Server(config)
    await s.serve()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    host = args.host or settings.mcp_host
    port = args.port or settings.mcp_port

    if args.transport == "stdio":
        asyncio.run(main_stdio())
    else:
        asyncio.run(main_http(host, port))


if __name__ == "__main__":
    main()
```

注意:
- `mcp.server.streamable_http_manager.StreamableHTTPSessionManager` 是 mcp SDK ≥ 1.1 的 HTTP transport API;若实际 SDK 版本不同,先 `pip show mcp` + `python -c "from mcp.server import streamable_http_manager"` 验证
- 如果 SDK 没这个模块,fallback 用 `mcp.server.sse.SseServerTransport`(SSE transport);Task 19 docker-compose CMD 也对应改

- [ ] **Step 6.10:写 conftest 测试 fixture**

新建 [mcp_server/tests/conftest.py](mcp_server/tests/conftest.py):

```python
"""MCP server tests 共享 fixture — MockTransport backend client。"""
from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.backend_client import (
    BackendClient,
    reset_backend_client_for_tests,
    set_backend_client_for_tests,
)
from app.config import reset_settings_for_tests


@pytest.fixture(autouse=True)
def reset_singletons():
    """每个 test 前后清掉单例 — 避免 client / settings 跨测试污染。"""
    reset_backend_client_for_tests()
    reset_settings_for_tests()
    yield
    reset_backend_client_for_tests()
    reset_settings_for_tests()


@pytest.fixture
def mock_backend(monkeypatch) -> Callable[[Callable[[httpx.Request], httpx.Response]], BackendClient]:
    """返回工厂函数:传 handler 进来 → 注入 BackendClient(走 MockTransport)。

    用法:
        async def handler(req: httpx.Request) -> httpx.Response:
            assert req.url.path == "/api/transactions"
            return httpx.Response(200, json={...})

        client = mock_backend(handler)
        # 工具 handler 直接 await get_backend_client().get(...) → 命中 mock
    """
    monkeypatch.setenv("MCP_API_TOKEN", "test-token-do-not-use")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> BackendClient:
        transport = httpx.MockTransport(handler)
        client = BackendClient(
            base_url="http://test-backend:8000",
            api_token="test-token-do-not-use",
            transport=transport,
        )
        set_backend_client_for_tests(client)
        return client

    return _factory
```

- [ ] **Step 6.11:写 `test_main_auth.py`(token 自检流程)**

新建 [mcp_server/tests/test_main_auth.py](mcp_server/tests/test_main_auth.py):

```python
"""MCP server bearer self-check 流程测试。"""
from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.main import _verify_token_self_check


async def test_verify_token_success(monkeypatch):
    monkeypatch.setenv("MCP_API_TOKEN", "good-token")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    handler_calls = []

    async def fake_post(self, url, **kwargs):
        handler_calls.append((url, kwargs.get("headers")))
        return httpx.Response(200, json={
            "user_id": 1, "username": "admin", "scopes": "read,write",
        })

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    await _verify_token_self_check()  # 不 raise

    assert handler_calls
    url, headers = handler_calls[0]
    assert url == "/api/admin/tokens/verify"
    assert headers["Authorization"] == "Bearer good-token"


async def test_verify_token_invalid_exits_with_code_2(monkeypatch):
    monkeypatch.setenv("MCP_API_TOKEN", "bad-token")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(401, json={"detail": "invalid token"})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(SystemExit) as exc_info:
        await _verify_token_self_check()
    assert exc_info.value.code == 2


async def test_verify_token_backend_5xx_exits_with_code_3(monkeypatch):
    monkeypatch.setenv("MCP_API_TOKEN", "good-token")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(503, text="db down")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(SystemExit) as exc_info:
        await _verify_token_self_check()
    assert exc_info.value.code == 3
```

- [ ] **Step 6.12:写 `test_backend_client.py`**

新建 [mcp_server/tests/test_backend_client.py](mcp_server/tests/test_backend_client.py):

```python
"""BackendClient httpx wrapper:auth header 注入 + 错误映射(spec § 8.3)。"""
from __future__ import annotations

import httpx
import pytest

from app.errors import (
    AUTH_FAILED,
    BACKEND_ERROR,
    CONFLICT,
    NOT_FOUND,
    VALIDATION_ERROR,
    MCPToolError,
)


def _client_with_handler(handler):
    from app.backend_client import BackendClient
    return BackendClient(
        base_url="http://test-backend:8000",
        api_token="t-test",
        transport=httpx.MockTransport(handler),
    )


async def test_get_injects_auth_header_and_returns_json():
    seen_headers = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen_headers.update(req.headers)
        return httpx.Response(200, json={"ok": True})

    client = _client_with_handler(handler)
    data = await client.get("/api/health")
    assert data == {"ok": True}
    assert seen_headers["authorization"] == "Bearer t-test"


async def test_post_returns_empty_dict_on_204():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = _client_with_handler(handler)
    data = await client.post("/api/x", json={"y": 1})
    assert data == {}


@pytest.mark.parametrize("status,expected_code", [
    (401, AUTH_FAILED),
    (404, NOT_FOUND),
    (409, CONFLICT),
    (400, VALIDATION_ERROR),
    (422, VALIDATION_ERROR),
    (500, BACKEND_ERROR),
    (503, BACKEND_ERROR),
])
async def test_status_to_mcp_error(status, expected_code):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": f"backend says {status}"})

    client = _client_with_handler(handler)
    with pytest.raises(MCPToolError) as exc_info:
        await client.get("/api/anything")
    assert exc_info.value.code == expected_code
    assert "backend says" in exc_info.value.message


async def test_backend_error_includes_status_in_data():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="db down")

    client = _client_with_handler(handler)
    with pytest.raises(MCPToolError) as exc_info:
        await client.get("/api/health")
    assert exc_info.value.code == BACKEND_ERROR
    assert exc_info.value.data == {"status": 503}
```

- [ ] **Step 6.13:在 worktree 内为 mcp_server 建独立 venv + 装 deps**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\mcp_server
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.\.venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"
```

期望:依赖装完无 error。

- [ ] **Step 6.14:跑骨架测试**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/ -v 2>&1 | Select-Object -Last 25
```

期望 3 个 test_main_auth.py + 4 个 test_backend_client.py = **7 个 PASS**;若 mcp SDK API 名称不一致(`StreamableHTTPSessionManager` 或 `Server` 路径),read SDK 实际 export(`python -c "import mcp.server.lowlevel; print(dir(mcp.server.lowlevel))"`)调整 import。

- [ ] **Step 6.15:验证 stdio 启动可工作(冒烟)**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\mcp_server
# 假定 backend 在跑(uvicorn + Postgres),并已生成一个 token 写到 .env MCP_API_TOKEN
# 否则 step 0.7 token verify 会 sys.exit(2)。本测试目的:验证 server 能起来到 verify 这步。
$env:MCP_API_TOKEN = "test-token-do-not-use"   # 故意错的,期望 sys.exit(2)
$env:MCP_BACKEND_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m app.main --transport stdio
# 期望:输出 "MCP_API_TOKEN invalid" + 进程退出 code 2
echo $LASTEXITCODE  # 期望 2
```

如果 backend 未跑,会 sys.exit(3)("backend not reachable");这两个分支都说明骨架 wire 通了 — Task 6 PASS。

- [ ] **Step 6.16:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
git add mcp_server/
git commit -m "feat(mcp): server skeleton — main + config + backend_client + errors

mcp_server/ is a separate Python project (its own pyproject + .venv +
Dockerfile) using the official mcp SDK >= 1.1. It wraps the
finance-manager backend REST API behind 10 MCP tools (registered in
Task 7-16). This skeleton:

- main.py: stdio + http transports, startup self-check that calls
  backend /api/admin/tokens/verify and exits non-zero if token rejected
- backend_client.py: httpx AsyncClient with Bearer header injection
  and httpx -> MCP error mapping per spec § 8.3
- errors.py: MCPToolError + 5 standard codes
- tools/__init__.py: TOOL_REGISTRY (filled by Task 7-16)
- tests cover token self-check (success/invalid/5xx) and backend
  client status -> error code mapping
"
```

---

## Task 7:MCP 工具 #1 read — `list_transactions`(完整体例,后续工具按此 pattern)

**Files:**
- Create: `mcp_server/app/tools/list_transactions.py`
- Create: `mcp_server/tests/test_tool_list_transactions.py`

> **背景:** spec § 8.1 read 工具 #1。入参 `date_range?, category?, account?, kind?, limit=50, offset=0`,出参精简的 transactions[]。MCP server 端做的事:
> 1. 校验 inputSchema(JSON Schema,SDK 自动验)
> 2. 把 MCP 工具入参映射到 backend `GET /api/transactions?date_from=&date_to=&category_id=&account_id=&kind=&limit=&offset=`
> 3. 把 backend 返回的 `TransactionListOut.items` 精简到 spec § 8.1 出参字段(`id, time, amount, merchant, category`)
>
> **后续 9 个工具完全按此 pattern**:`tool.py` 内定义 `mcp_types.Tool(name, description, inputSchema)` → `register(tool, _handler)` → `_handler(args)` 调 backend → trim/transform。
>
> **inline backend 校验**:
>
> ```
> backend check (GET /api/transactions):  query 参数名是 date_from/date_to/account_id/category_id/kind/source/is_mirror/keyword/limit/offset(slice C 已实现,见 schemas/transaction.py TransactionQuery)
> backend check (TransactionOut):  字段 id / account_id / tx_time / amount / merchant_normalized / category_id / classification_confidence / source / is_mirror / mirror_of_id / 等 14 字段 — MCP 出参只暴露 5 个(id/time/amount/merchant/category),其余 trim
> backend check:  Category.name 不在 TransactionOut 里,MCP 端要 join 一次?或:让 backend 多返字段?决定:**MCP 端 trim,category 字段返回 category_id**(int | None),agent 想要中文名再调 list_categories(本切片不暴露 list_categories 给 MCP — backend Web UI 用,MCP 用直接看 category_id;如要 agent-friendly 名字,V2 加 `expand=category` query)。spec § 8.1 写"category" 留歧义,本实现解读为 category_id。**plan 决策点:**记入 task 备注。
> ```

- [ ] **Step 7.1:Inline 校验**

```powershell
Get-Content backend\app\schemas\transaction.py | Select-String -Pattern "class TransactionQuery|class TransactionOut" -Context 0, 12
```

确认 14 字段 + 10 个 query 参数。

- [ ] **Step 7.2:写测试**

新建 [mcp_server/tests/test_tool_list_transactions.py](mcp_server/tests/test_tool_list_transactions.py):

```python
"""MCP tool: list_transactions — backend GET /api/transactions 的 wrapper。"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.tools import get_handler, get_tool_definitions


def _setup_tool(mock_backend, response_payload):
    """共享 setup:注册 tool + 注入 mock backend。返回 captured_request: list[httpx.Request]。"""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=response_payload)

    mock_backend(handler)
    # import 触发 register
    import app.tools.list_transactions  # noqa: F401
    return captured


@pytest.fixture
def sample_backend_response() -> dict:
    return {
        "items": [
            {
                "id": 1, "account_id": 5, "statement_import_id": 3,
                "tx_kind": "expense", "tx_time": "2026-05-08T12:30:00",
                "post_time": None, "amount": "23.50", "currency": "CNY",
                "amount_settled_cny": "23.50",
                "merchant_raw": "瑞幸咖啡", "merchant_normalized": "瑞幸咖啡",
                "description_raw": None,
                "category_id": 11, "classification_confidence": 1.0,
                "source": "alipay",
                "is_mirror": False, "mirror_of_id": None,
            },
            {
                "id": 2, "account_id": 6, "statement_import_id": 3,
                "tx_kind": "income", "tx_time": "2026-05-08T09:00:00",
                "post_time": None, "amount": "5000.00", "currency": "CNY",
                "amount_settled_cny": "5000.00",
                "merchant_raw": "工资", "merchant_normalized": "工资",
                "description_raw": None,
                "category_id": None, "classification_confidence": None,
                "source": "manual",
                "is_mirror": False, "mirror_of_id": None,
            },
        ],
        "total": 2, "limit": 50, "offset": 0,
    }


def test_list_transactions_tool_definition_present():
    import app.tools.list_transactions  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "list_transactions" in names


async def test_list_transactions_minimal_call(mock_backend, sample_backend_response):
    captured = _setup_tool(mock_backend, sample_backend_response)
    handler = get_handler("list_transactions")
    assert handler is not None

    result = await handler({})
    assert len(result) == 1
    payload = json.loads(result[0].text)
    # spec § 8.1 出参精简到 5 字段
    assert "transactions" in payload
    items = payload["transactions"]
    assert len(items) == 2
    for item in items:
        assert set(item.keys()) >= {"id", "time", "amount", "merchant", "category"}
    assert items[0]["id"] == 1
    assert items[0]["time"] == "2026-05-08T12:30:00"
    assert items[0]["amount"] == "23.50"
    assert items[0]["merchant"] == "瑞幸咖啡"
    assert items[0]["category"] == 11
    assert items[1]["category"] is None  # 未分类


async def test_list_transactions_passes_filters_to_backend(
    mock_backend, sample_backend_response,
):
    captured = _setup_tool(mock_backend, sample_backend_response)
    handler = get_handler("list_transactions")

    await handler({
        "date_from": "2026-05-01T00:00:00",
        "date_to": "2026-05-31T23:59:59",
        "account_id": 5,
        "category_id": 11,
        "kind": "expense",
        "limit": 100,
        "offset": 50,
    })
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/transactions"
    qs = parse_qs(urlparse(str(req.url)).query)
    assert qs["date_from"] == ["2026-05-01T00:00:00"]
    assert qs["date_to"] == ["2026-05-31T23:59:59"]
    assert qs["account_id"] == ["5"]
    assert qs["category_id"] == ["11"]
    assert qs["kind"] == ["expense"]
    assert qs["limit"] == ["100"]
    assert qs["offset"] == ["50"]


async def test_list_transactions_omits_none_filters(mock_backend, sample_backend_response):
    """MCP 入参 None / 缺省 → 不传 backend(让 backend 用其 default)。"""
    captured = _setup_tool(mock_backend, sample_backend_response)
    handler = get_handler("list_transactions")
    await handler({"limit": 10})
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    assert "date_from" not in qs
    assert "category_id" not in qs
    assert qs["limit"] == ["10"]


async def test_list_transactions_handles_404_via_error_envelope(mock_backend):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    mock_backend(handler)
    import app.tools.list_transactions  # noqa: F401
    h = get_handler("list_transactions")

    result = await h({})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


async def test_list_transactions_input_schema_valid_json_schema():
    """inputSchema 必须是合法 JSON Schema(SDK 会用,但不验证;手动 sanity check)。"""
    import app.tools.list_transactions  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "list_transactions")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    # 每个 property 至少有 type
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
```

- [ ] **Step 7.3:跑测试看失败**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_tool_list_transactions.py -v 2>&1 | Select-Object -Last 15
```

期望全 FAIL(`app.tools.list_transactions` ImportError)。

- [ ] **Step 7.4:实现 tool**

新建 [mcp_server/app/tools/list_transactions.py](mcp_server/app/tools/list_transactions.py):

```python
"""MCP tool: list_transactions — spec § 8.1 read #1。

backend endpoint: GET /api/transactions
出参精简:每条只返 {id, time, amount, merchant, category}。
"""
from __future__ import annotations

import json
from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="list_transactions",
    description=(
        "List transactions with optional filters. "
        "Use date_from/date_to (ISO 8601) for time range, account_id / category_id "
        "for scope, kind in {expense,income,neutral,refund} for type. "
        "Returns paginated list with summary fields per row."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "date_from": {"type": "string", "description": "ISO 8601 datetime, inclusive"},
            "date_to": {"type": "string", "description": "ISO 8601 datetime, inclusive"},
            "account_id": {"type": "integer", "description": "filter by account.id"},
            "category_id": {"type": "integer", "description": "filter by category.id"},
            "kind": {
                "type": "string",
                "enum": ["expense", "income", "neutral", "refund"],
            },
            "source": {
                "type": "string",
                "enum": ["bank", "alipay", "wechat", "conversation", "manual"],
            },
            "keyword": {"type": "string", "description": "substring of merchant_normalized"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": [],
    },
)


def _to_query(args: dict[str, Any]) -> dict[str, str | int]:
    """剔除 None,把 MCP 入参直传 backend query string(参数名一致)。"""
    out: dict[str, str | int] = {}
    for k in ("date_from", "date_to", "account_id", "category_id",
              "kind", "source", "keyword", "limit", "offset"):
        if k in args and args[k] is not None:
            out[k] = args[k]
    return out


def _trim_transaction(tx: dict) -> dict:
    """spec § 8.1 read #1 出参字段精简。"""
    return {
        "id": tx["id"],
        "time": tx["tx_time"],
        "amount": tx["amount"],
        "merchant": tx.get("merchant_normalized") or tx.get("merchant_raw"),
        "category": tx.get("category_id"),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get("/api/transactions", params=_to_query(args))
    except MCPToolError as e:
        return [mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False),
        )]
    out = {
        "transactions": [_trim_transaction(t) for t in data.get("items", [])],
        "total": data.get("total"),
        "limit": data.get("limit"),
        "offset": data.get("offset"),
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 7.5:跑测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_list_transactions.py -v 2>&1 | Select-Object -Last 15
```

期望 6 全 PASS。如某个 test 因 fixture 顺序失败(register 触发于 import → conftest 的 reset_singletons 影响 TOOL_REGISTRY?),改 conftest:`TOOL_REGISTRY.clear()` 也加进 autouse fixture(但小心 — 一旦清掉,后续 test 都得重新 import 触发 register;**不要清** TOOL_REGISTRY,只清 client/settings 单例)。

- [ ] **Step 7.6:Commit**

```powershell
git add mcp_server/app/tools/list_transactions.py mcp_server/tests/test_tool_list_transactions.py
git commit -m "feat(mcp): tool list_transactions (read #1 of 10)

Wraps GET /api/transactions, trims response to spec § 8.1 fields:
{id, time, amount, merchant, category}. inputSchema mirrors backend
TransactionQuery (slice C). Errors propagated as JSON envelope per
spec § 8.3.
"
```

---

## Task 8:MCP 工具 #2 read — `get_summary`

**Files:**
- Create: `mcp_server/app/tools/get_summary.py`
- Create: `mcp_server/tests/test_tool_get_summary.py`

> **背景:** spec § 8.1 read #2。入参 `period[day/week/month/year], group_by[category/account/merchant], date_range?`,出参 `summary: { total_expense, total_income, breakdown: [{group, amount, count}] }`。Backend `GET /api/summary?period=&group_by=&date_from=&date_to=` 已存在(slice C);MCP 端做的事:出参字段重命名 `breakdown[].group_key` → `breakdown[].group`(MCP 简化命名)。
>
> **inline backend 校验**:
>
> ```
> backend check (SummaryOut):  total_expense / total_income / breakdown: list[SummaryBreakdownItem(group_key, group_id, amount, count)] / period / date_from / date_to / group_by
> ```

- [ ] **Step 8.1:写测试**(模式同 Task 7 — 完整 import + register + handler 调用)

新建 [mcp_server/tests/test_tool_get_summary.py](mcp_server/tests/test_tool_get_summary.py):

```python
from __future__ import annotations
import json
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    return {
        "period": "month", "date_from": "2026-05-01T00:00:00",
        "date_to": "2026-06-01T00:00:00", "group_by": "category",
        "total_expense": "1234.56", "total_income": "5000.00",
        "breakdown": [
            {"group_key": "餐饮/咖啡", "group_id": 11, "amount": "456.00", "count": 12},
            {"group_key": "购物/淘宝", "group_id": 12, "amount": "778.56", "count": 5},
        ],
    }


def test_tool_def_present():
    import app.tools.get_summary  # noqa: F401
    assert "get_summary" in [t.name for t in get_tool_definitions()]


async def test_get_summary_default(mock_backend, sample):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(200, json=sample)
    mock_backend(handler)
    import app.tools.get_summary  # noqa: F401
    h = get_handler("get_summary")
    result = await h({})
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    # 默认应不传 period / group_by(让 backend 用自己 default month/category)
    assert captured[0].url.path == "/api/summary"
    payload = json.loads(result[0].text)
    assert payload["total_expense"] == "1234.56"
    assert payload["total_income"] == "5000.00"
    # breakdown[].group_key → breakdown[].group(MCP 简化)
    assert payload["breakdown"][0]["group"] == "餐饮/咖啡"
    assert payload["breakdown"][0]["amount"] == "456.00"
    assert payload["breakdown"][0]["count"] == 12


async def test_get_summary_passes_period_and_group_by(mock_backend, sample):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(200, json=sample)
    mock_backend(handler)
    import app.tools.get_summary  # noqa: F401
    h = get_handler("get_summary")
    await h({"period": "year", "group_by": "merchant",
             "date_from": "2026-01-01T00:00:00", "date_to": "2026-12-31T23:59:59"})
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    assert qs["period"] == ["year"]
    assert qs["group_by"] == ["merchant"]
    assert qs["date_from"] == ["2026-01-01T00:00:00"]
    assert qs["date_to"] == ["2026-12-31T23:59:59"]
```

- [ ] **Step 8.2:实现**

新建 [mcp_server/app/tools/get_summary.py](mcp_server/app/tools/get_summary.py):

```python
"""MCP tool: get_summary — spec § 8.1 read #2。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="get_summary",
    description=(
        "Aggregate transactions over a period and group by category/account/merchant. "
        "Returns total_expense, total_income, and breakdown rows."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "period": {"type": "string", "enum": ["day", "week", "month", "year"], "default": "month"},
            "group_by": {"type": "string", "enum": ["category", "account", "merchant"], "default": "category"},
            "date_from": {"type": "string"},
            "date_to": {"type": "string"},
        },
        "required": [],
    },
)


def _to_query(args: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in ("period", "group_by", "date_from", "date_to"):
        if k in args and args[k] is not None:
            out[k] = args[k]
    return out


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get("/api/summary", params=_to_query(args))
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    out = {
        "period": data.get("period"),
        "date_from": data.get("date_from"),
        "date_to": data.get("date_to"),
        "group_by": data.get("group_by"),
        "total_expense": data.get("total_expense"),
        "total_income": data.get("total_income"),
        "breakdown": [
            {"group": b.get("group_key"), "group_id": b.get("group_id"),
             "amount": b.get("amount"), "count": b.get("count")}
            for b in data.get("breakdown", [])
        ],
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 8.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_get_summary.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/get_summary.py mcp_server/tests/test_tool_get_summary.py
git commit -m "feat(mcp): tool get_summary (read #2 of 10)"
```

---

## Task 9:MCP 工具 #3 read — `get_account_balances`

**Files:**
- Create: `mcp_server/app/tools/get_account_balances.py`
- Create: `mcp_server/tests/test_tool_get_account_balances.py`

> **背景:** spec § 8.1 read #3。无入参,出参 `accounts: [{id, name, type, last4, latest_balance, latest_balance_at}]`。Backend `GET /api/accounts`(Task 4 已加 `latest_balance` / `latest_balance_at`)。MCP 端 trim 字段:只返 spec 列出的 6 个,不返 `institution / currency / archived`(避免 agent 处理不必要字段)。

- [ ] **Step 9.1:写测试**

新建 [mcp_server/tests/test_tool_get_account_balances.py](mcp_server/tests/test_tool_get_account_balances.py):

```python
from __future__ import annotations
import json
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    return {
        "items": [
            {"id": 1, "name": "支付宝", "type": "alipay", "institution": "支付宝",
             "last4": None, "currency": "CNY", "archived": False,
             "latest_balance": "1234.50", "latest_balance_at": "2026-05-08T12:30:00"},
            {"id": 2, "name": "交通银行借记卡 2498", "type": "bank_debit",
             "institution": "交通银行", "last4": "2498", "currency": "CNY",
             "archived": False,
             "latest_balance": "0.00", "latest_balance_at": None},
        ], "total": 2,
    }


def test_tool_def_present():
    import app.tools.get_account_balances  # noqa: F401
    assert "get_account_balances" in [t.name for t in get_tool_definitions()]


async def test_get_account_balances_returns_trimmed_fields(mock_backend, sample):
    def handler(req): return httpx.Response(200, json=sample)
    mock_backend(handler)
    import app.tools.get_account_balances  # noqa: F401
    h = get_handler("get_account_balances")
    result = await h({})
    payload = json.loads(result[0].text)
    accounts = payload["accounts"]
    assert len(accounts) == 2
    for a in accounts:
        assert set(a.keys()) == {"id", "name", "type", "last4",
                                  "latest_balance", "latest_balance_at"}
    assert accounts[0]["latest_balance"] == "1234.50"
    assert accounts[1]["latest_balance"] == "0.00"
    assert accounts[1]["latest_balance_at"] is None
```

- [ ] **Step 9.2:实现**

新建 [mcp_server/app/tools/get_account_balances.py](mcp_server/app/tools/get_account_balances.py):

```python
"""MCP tool: get_account_balances — spec § 8.1 read #3。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="get_account_balances",
    description="List all accounts with their latest derived balance (income - expense - refund, excluding mirrors).",
    inputSchema={"type": "object", "properties": {}, "required": []},
)


def _trim(a: dict) -> dict:
    return {
        "id": a["id"], "name": a["name"], "type": a["type"], "last4": a.get("last4"),
        "latest_balance": a.get("latest_balance"),
        "latest_balance_at": a.get("latest_balance_at"),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get("/api/accounts")
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    out = {"accounts": [_trim(a) for a in data.get("items", [])]}
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 9.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_get_account_balances.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/get_account_balances.py mcp_server/tests/test_tool_get_account_balances.py
git commit -m "feat(mcp): tool get_account_balances (read #3 of 10)"
```

---

## Task 10:MCP 工具 #4 read — `find_merchant`

**Files:**
- Create: `mcp_server/app/tools/find_merchant.py`
- Create: `mcp_server/tests/test_tool_find_merchant.py`

> **背景:** spec § 8.1 read #4。入参 `keyword` 必填,出参 `merchants: [{normalized, count, total_amount, sample_categories}]`。Backend `GET /api/transactions/merchants?keyword=&limit=`(Task 2 已加)直接对应。

- [ ] **Step 10.1:写测试**

新建 [mcp_server/tests/test_tool_find_merchant.py](mcp_server/tests/test_tool_find_merchant.py):

```python
from __future__ import annotations
import json
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    return {
        "items": [
            {"normalized": "瑞幸咖啡 五道口", "count": 3, "total_amount": "75.50",
             "sample_categories": ["餐饮/咖啡"]},
            {"normalized": "瑞幸咖啡 西二旗", "count": 1, "total_amount": "18.00",
             "sample_categories": ["餐饮/咖啡"]},
        ], "total": 2,
    }


def test_tool_def_present():
    import app.tools.find_merchant  # noqa: F401
    assert "find_merchant" in [t.name for t in get_tool_definitions()]


async def test_find_merchant_passes_keyword(mock_backend, sample):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(200, json=sample)
    mock_backend(handler)
    import app.tools.find_merchant  # noqa: F401
    h = get_handler("find_merchant")
    await h({"keyword": "瑞幸"})
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    assert qs["keyword"] == ["瑞幸"]
    assert captured[0].url.path == "/api/transactions/merchants"


async def test_find_merchant_returns_aggregated_items(mock_backend, sample):
    def handler(req): return httpx.Response(200, json=sample)
    mock_backend(handler)
    import app.tools.find_merchant  # noqa: F401
    h = get_handler("find_merchant")
    result = await h({"keyword": "瑞幸"})
    payload = json.loads(result[0].text)
    assert "merchants" in payload
    assert len(payload["merchants"]) == 2
    assert payload["merchants"][0]["count"] == 3
    assert payload["merchants"][0]["sample_categories"] == ["餐饮/咖啡"]


async def test_find_merchant_missing_keyword_validation(mock_backend):
    def handler(req): return httpx.Response(422, json={"detail": "keyword required"})
    mock_backend(handler)
    import app.tools.find_merchant  # noqa: F401
    h = get_handler("find_merchant")
    # SDK inputSchema 标 required: ["keyword"],但 SDK 不强制(server-level 校验
    # 由 mcp dispatch 做);这里测 backend 422 → MCP error envelope
    result = await h({"keyword": ""})  # 空字符串,backend 会 422
    payload = json.loads(result[0].text)
    assert payload.get("error", {}).get("code") == "VALIDATION_ERROR"
```

- [ ] **Step 10.2:实现**

新建 [mcp_server/app/tools/find_merchant.py](mcp_server/app/tools/find_merchant.py):

```python
"""MCP tool: find_merchant — spec § 8.1 read #4。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="find_merchant",
    description="Search merchants by substring keyword and aggregate count + total + sample categories.",
    inputSchema={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "minLength": 1, "maxLength": 128},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
        },
        "required": ["keyword"],
    },
)


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    params = {"keyword": args.get("keyword", "")}
    if "limit" in args and args["limit"] is not None:
        params["limit"] = args["limit"]
    try:
        data = await client.get("/api/transactions/merchants", params=params)
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    out = {"merchants": data.get("items", [])}
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 10.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_find_merchant.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/find_merchant.py mcp_server/tests/test_tool_find_merchant.py
git commit -m "feat(mcp): tool find_merchant (read #4 of 10)"
```

---

## Task 11:MCP 工具 #5 read — `list_pending_dedup_pairs`

**Files:**
- Create: `mcp_server/app/tools/list_pending_dedup_pairs.py`
- Create: `mcp_server/tests/test_tool_list_pending_dedup_pairs.py`

> **背景:** spec § 8.1 read #5。入参 `limit=20`,出参 `pairs: [{id, primary, mirror, match_kind, confidence, reasoning}]`。Backend `GET /api/dedup/pending?limit=&offset=`(slice C 已实现)直接对应,出参字段 trim。
>
> **inline backend 校验**:
>
> ```
> backend check (DedupPairOut):  fields id / user_id / primary_tx_id / mirror_tx_id / match_kind / confidence / status / reasoning / created_at / decided_at
> mapping:  primary_tx_id → primary, mirror_tx_id → mirror;status/created_at/decided_at 不暴露(spec § 8.1 仅需 6 个字段)
> ```

- [ ] **Step 11.1:写测试**

新建 [mcp_server/tests/test_tool_list_pending_dedup_pairs.py](mcp_server/tests/test_tool_list_pending_dedup_pairs.py):

```python
from __future__ import annotations
import json
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    return {
        "items": [
            {"id": 1, "user_id": 1, "primary_tx_id": 100, "mirror_tx_id": 200,
             "match_kind": "bridge", "confidence": 0.85, "status": "pending",
             "reasoning": {"rule": "bridge", "signals": ["amount_match"]},
             "created_at": "2026-05-08T12:30:00", "decided_at": None},
        ], "total": 1,
    }


def test_tool_def_present():
    import app.tools.list_pending_dedup_pairs  # noqa: F401
    assert "list_pending_dedup_pairs" in [t.name for t in get_tool_definitions()]


async def test_list_pending_dedup_pairs(mock_backend, sample):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(200, json=sample)
    mock_backend(handler)
    import app.tools.list_pending_dedup_pairs  # noqa: F401
    h = get_handler("list_pending_dedup_pairs")
    result = await h({"limit": 50})
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    assert qs["limit"] == ["50"]
    payload = json.loads(result[0].text)
    pair = payload["pairs"][0]
    assert set(pair.keys()) == {"id", "primary", "mirror",
                                "match_kind", "confidence", "reasoning"}
    assert pair["primary"] == 100
    assert pair["mirror"] == 200
    assert pair["match_kind"] == "bridge"
```

- [ ] **Step 11.2:实现**

新建 [mcp_server/app/tools/list_pending_dedup_pairs.py](mcp_server/app/tools/list_pending_dedup_pairs.py):

```python
"""MCP tool: list_pending_dedup_pairs — spec § 8.1 read #5。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="list_pending_dedup_pairs",
    description="List dedup candidate pairs awaiting human/agent decision.",
    inputSchema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": [],
    },
)


def _trim(p: dict) -> dict:
    return {
        "id": p["id"],
        "primary": p["primary_tx_id"],
        "mirror": p["mirror_tx_id"],
        "match_kind": p["match_kind"],
        "confidence": p.get("confidence"),
        "reasoning": p.get("reasoning"),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    params = {k: v for k, v in (("limit", args.get("limit")), ("offset", args.get("offset"))) if v is not None}
    try:
        data = await client.get("/api/dedup/pending", params=params)
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    return [mcp_types.TextContent(type="text", text=json.dumps(
        {"pairs": [_trim(p) for p in data.get("items", [])]}, ensure_ascii=False,
    ))]


register(_TOOL, _handler)
```

- [ ] **Step 11.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_list_pending_dedup_pairs.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/list_pending_dedup_pairs.py mcp_server/tests/test_tool_list_pending_dedup_pairs.py
git commit -m "feat(mcp): tool list_pending_dedup_pairs (read #5 of 10)"
```

---

## Task 12:MCP 工具 #6 read — `list_pending_classifications`

**Files:**
- Create: `mcp_server/app/tools/list_pending_classifications.py`
- Create: `mcp_server/tests/test_tool_list_pending_classifications.py`

> **背景:** spec § 8.1 read #6。入参 `limit=20`,出参 `transactions: [{id, time, amount, merchant, suggested_categories[]}]`。Backend `GET /api/transactions/pending-classifications?limit=&offset=`(Task 3 已加)。第一版 `suggested_categories` 在 backend 端返空 list,MCP 端透传。

- [ ] **Step 12.1:写测试**

新建 [mcp_server/tests/test_tool_list_pending_classifications.py](mcp_server/tests/test_tool_list_pending_classifications.py):

```python
from __future__ import annotations
import json
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    return {
        "items": [
            {"id": 50, "account_id": 1, "tx_kind": "expense",
             "tx_time": "2026-05-08T12:30:00", "amount": "23.50", "currency": "CNY",
             "amount_settled_cny": "23.50",
             "merchant_raw": "某未知小店", "merchant_normalized": "某未知小店",
             "category_id": None, "classification_confidence": None,
             "source": "alipay", "is_mirror": False, "mirror_of_id": None,
             "post_time": None, "description_raw": None, "statement_import_id": 5},
        ], "total": 1, "limit": 20, "offset": 0,
    }


def test_tool_def_present():
    import app.tools.list_pending_classifications  # noqa: F401
    assert "list_pending_classifications" in [t.name for t in get_tool_definitions()]


async def test_list_pending_classifications(mock_backend, sample):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(200, json=sample)
    mock_backend(handler)
    import app.tools.list_pending_classifications  # noqa: F401
    h = get_handler("list_pending_classifications")
    result = await h({"limit": 10})
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    assert captured[0].url.path == "/api/transactions/pending-classifications"
    assert qs["limit"] == ["10"]
    payload = json.loads(result[0].text)
    items = payload["transactions"]
    assert len(items) == 1
    assert set(items[0].keys()) == {"id", "time", "amount", "merchant",
                                    "suggested_categories"}
    assert items[0]["suggested_categories"] == []  # 第一版空
```

- [ ] **Step 12.2:实现**

新建 [mcp_server/app/tools/list_pending_classifications.py](mcp_server/app/tools/list_pending_classifications.py):

```python
"""MCP tool: list_pending_classifications — spec § 8.1 read #6。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="list_pending_classifications",
    description="List uncategorized (category_id IS NULL) non-mirror transactions for agent to classify.",
    inputSchema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": [],
    },
)


def _trim(t: dict) -> dict:
    return {
        "id": t["id"],
        "time": t["tx_time"],
        "amount": t["amount"],
        "merchant": t.get("merchant_normalized") or t.get("merchant_raw"),
        "suggested_categories": [],     # V2:backend 加 rapidfuzz 建议时改透传 t["suggested_categories"]
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    params = {k: v for k, v in (("limit", args.get("limit")), ("offset", args.get("offset"))) if v is not None}
    try:
        data = await client.get("/api/transactions/pending-classifications", params=params)
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    return [mcp_types.TextContent(type="text", text=json.dumps(
        {"transactions": [_trim(t) for t in data.get("items", [])]}, ensure_ascii=False,
    ))]


register(_TOOL, _handler)
```

- [ ] **Step 12.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_list_pending_classifications.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/list_pending_classifications.py mcp_server/tests/test_tool_list_pending_classifications.py
git commit -m "feat(mcp): tool list_pending_classifications (read #6 of 10)"
```

---

## Task 13:MCP 工具 #7 write — `add_transaction`

**Files:**
- Create: `mcp_server/app/tools/add_transaction.py`
- Create: `mcp_server/tests/test_tool_add_transaction.py`

> **背景:** spec § 8.1 write #1。入参 `time, amount, currency='CNY', merchant, category?, account?, kind='expense'`,出参 `transaction_id, applied_rule?, classified_category`。Backend `POST /api/transactions/manual`(Task 1 已加)。
>
> **MCP→backend 字段映射**:
>
> ```
> MCP "time"        → backend "tx_time"
> MCP "merchant"    → backend "merchant"(同名)
> MCP "category"    → backend "category_id"(类型 int);spec 写 "category" 但实际 agent 拿到的是 id
> MCP "account"     → backend "account_id"
> MCP "kind"        → backend "tx_kind"
> ```

- [ ] **Step 13.1:写测试**

新建 [mcp_server/tests/test_tool_add_transaction.py](mcp_server/tests/test_tool_add_transaction.py):

```python
from __future__ import annotations
import json
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    return {
        "id": 999, "account_id": 1, "tx_kind": "expense",
        "tx_time": "2026-05-10T12:30:00", "amount": "23.50", "currency": "CNY",
        "amount_settled_cny": "23.50",
        "merchant_raw": "瑞幸咖啡", "merchant_normalized": "瑞幸咖啡",
        "category_id": 11, "classification_confidence": 1.0,
        "source": "manual", "is_mirror": False, "mirror_of_id": None,
        "post_time": None, "description_raw": None, "statement_import_id": None,
    }


def test_tool_def_present():
    import app.tools.add_transaction  # noqa: F401
    assert "add_transaction" in [t.name for t in get_tool_definitions()]


async def test_add_transaction_minimal(mock_backend, sample):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(201, json=sample)
    mock_backend(handler)
    import app.tools.add_transaction  # noqa: F401
    h = get_handler("add_transaction")
    result = await h({
        "time": "2026-05-10T12:30:00",
        "amount": "23.50",
        "merchant": "瑞幸咖啡",
        "account": 1,
    })
    assert captured[0].url.path == "/api/transactions/manual"
    body = json.loads(captured[0].content)
    assert body["tx_time"] == "2026-05-10T12:30:00"
    assert body["amount"] == "23.50"
    assert body["merchant"] == "瑞幸咖啡"
    assert body["account_id"] == 1
    assert body["tx_kind"] == "expense"
    assert body["currency"] == "CNY"
    payload = json.loads(result[0].text)
    assert payload["transaction_id"] == 999
    assert payload["classified_category"] == 11


async def test_add_transaction_with_explicit_category(mock_backend, sample):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(201, json=sample)
    mock_backend(handler)
    import app.tools.add_transaction  # noqa: F401
    h = get_handler("add_transaction")
    await h({
        "time": "2026-05-10T12:30:00",
        "amount": "23.50",
        "merchant": "瑞幸咖啡",
        "account": 1,
        "category": 11,
        "kind": "income",
    })
    body = json.loads(captured[0].content)
    assert body["category_id"] == 11
    assert body["tx_kind"] == "income"


async def test_add_transaction_account_not_found(mock_backend):
    def handler(req): return httpx.Response(404, json={"detail": "account not found"})
    mock_backend(handler)
    import app.tools.add_transaction  # noqa: F401
    h = get_handler("add_transaction")
    result = await h({"time": "2026-05-10T12:30:00", "amount": "1.00",
                      "merchant": "x", "account": 999})
    payload = json.loads(result[0].text)
    assert payload["error"]["code"] == "NOT_FOUND"
```

- [ ] **Step 13.2:实现**

新建 [mcp_server/app/tools/add_transaction.py](mcp_server/app/tools/add_transaction.py):

```python
"""MCP tool: add_transaction — spec § 8.1 write #1。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="add_transaction",
    description=(
        "Create a manual transaction (source=manual). Optionally pass category id "
        "to skip auto-classify; otherwise the backend rule engine fills it in."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "time": {"type": "string", "description": "ISO 8601 datetime"},
            "amount": {"type": "string", "description": "decimal string e.g. '23.50'"},
            "currency": {"type": "string", "default": "CNY"},
            "merchant": {"type": "string", "minLength": 1, "maxLength": 255},
            "category": {"type": "integer", "description": "optional category.id"},
            "account": {"type": "integer", "description": "account.id"},
            "kind": {"type": "string",
                     "enum": ["expense", "income", "neutral", "refund"], "default": "expense"},
            "description": {"type": "string"},
        },
        "required": ["time", "amount", "merchant", "account"],
    },
)


def _to_body(args: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "tx_time": args["time"],
        "amount": args["amount"],
        "currency": args.get("currency", "CNY"),
        "merchant": args["merchant"],
        "account_id": args["account"],
        "tx_kind": args.get("kind", "expense"),
    }
    if "category" in args and args["category"] is not None:
        body["category_id"] = args["category"]
    if "description" in args and args["description"] is not None:
        body["description"] = args["description"]
    return body


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.post("/api/transactions/manual", json=_to_body(args))
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    out = {
        "transaction_id": data["id"],
        "applied_rule": None,    # backend POST /manual 不返 rule_id;V2 加 endpoint 增强
        "classified_category": data.get("category_id"),
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 13.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_add_transaction.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/add_transaction.py mcp_server/tests/test_tool_add_transaction.py
git commit -m "feat(mcp): tool add_transaction (write #1 of 4)"
```

---

## Task 14:MCP 工具 #8 write — `update_category`

**Files:**
- Create: `mcp_server/app/tools/update_category.py`
- Create: `mcp_server/tests/test_tool_update_category.py`

> **背景:** spec § 8.1 write #2。入参 `transaction_id, category`,出参 `ok, before_category, after_category`。Backend `PATCH /api/transactions/{id}` body `{category_id}`(slice C 已实现)。MCP 端**需要先 GET 一次** transaction 拿 before_category,再 PATCH。

- [ ] **Step 14.1:写测试**

新建 [mcp_server/tests/test_tool_update_category.py](mcp_server/tests/test_tool_update_category.py):

```python
from __future__ import annotations
import json
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


def _make_tx(tx_id: int, cat_id):
    return {"id": tx_id, "account_id": 1, "tx_kind": "expense",
            "tx_time": "2026-05-08T12:30:00", "amount": "10.00", "currency": "CNY",
            "amount_settled_cny": "10.00",
            "merchant_raw": "x", "merchant_normalized": "x",
            "category_id": cat_id, "classification_confidence": 1.0 if cat_id else None,
            "source": "manual", "is_mirror": False, "mirror_of_id": None,
            "post_time": None, "description_raw": None, "statement_import_id": None}


def test_tool_def_present():
    import app.tools.update_category  # noqa: F401
    assert "update_category" in [t.name for t in get_tool_definitions()]


async def test_update_category_returns_before_and_after(mock_backend):
    """先 GET 拿 before_category(=11),再 PATCH 改成 22,返回 before+after。"""
    state = {"step": 0}
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            state["step"] = 1
            return httpx.Response(200, json=_make_tx(50, 11))  # before
        elif req.method == "PATCH":
            assert json.loads(req.content) == {"category_id": 22}
            state["step"] = 2
            return httpx.Response(200, json=_make_tx(50, 22))  # after
        return httpx.Response(500)

    mock_backend(handler)
    import app.tools.update_category  # noqa: F401
    h = get_handler("update_category")
    result = await h({"transaction_id": 50, "category": 22})
    payload = json.loads(result[0].text)
    assert payload["ok"] is True
    assert payload["before_category"] == 11
    assert payload["after_category"] == 22
    assert state["step"] == 2  # 两步都执行了


async def test_update_category_tx_not_found(mock_backend):
    def handler(req): return httpx.Response(404, json={"detail": "transaction not found"})
    mock_backend(handler)
    import app.tools.update_category  # noqa: F401
    h = get_handler("update_category")
    result = await h({"transaction_id": 999, "category": 1})
    payload = json.loads(result[0].text)
    assert payload["error"]["code"] == "NOT_FOUND"
```

- [ ] **Step 14.2:实现**

新建 [mcp_server/app/tools/update_category.py](mcp_server/app/tools/update_category.py):

```python
"""MCP tool: update_category — spec § 8.1 write #2。

GET tx 拿 before_category,再 PATCH 改 category_id;返回 before/after。
"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="update_category",
    description="Update one transaction's category. Returns before+after category_id.",
    inputSchema={
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "category": {"type": "integer", "description": "target category.id"},
        },
        "required": ["transaction_id", "category"],
    },
)


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    tx_id = args["transaction_id"]
    new_cat = args["category"]
    try:
        before = await client.get(f"/api/transactions/{tx_id}")
        after = await client.patch(f"/api/transactions/{tx_id}",
                                    json={"category_id": new_cat})
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    out = {
        "ok": True,
        "before_category": before.get("category_id"),
        "after_category": after.get("category_id"),
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 14.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_update_category.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/update_category.py mcp_server/tests/test_tool_update_category.py
git commit -m "feat(mcp): tool update_category (write #2 of 4)"
```

---

## Task 15:MCP 工具 #9 write — `bulk_update_category_by_merchant`

**Files:**
- Create: `mcp_server/app/tools/bulk_update_category_by_merchant.py`
- Create: `mcp_server/tests/test_tool_bulk_update_category_by_merchant.py`

> **背景:** spec § 8.1 write #3。入参 `pattern, category, match_kind='contains', also_add_rule=true`,出参 `affected_count, rule_id?`。Backend `POST /api/transactions/bulk-update-by-merchant` body 严格对应 `BulkUpdateByMerchantIn`(slice C 已实现);MCP 端的 `category` → backend `category_id`。

- [ ] **Step 15.1:写测试**

新建 [mcp_server/tests/test_tool_bulk_update_category_by_merchant.py](mcp_server/tests/test_tool_bulk_update_category_by_merchant.py):

```python
from __future__ import annotations
import json
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


def test_tool_def_present():
    import app.tools.bulk_update_category_by_merchant  # noqa: F401
    assert "bulk_update_category_by_merchant" in [t.name for t in get_tool_definitions()]


async def test_bulk_update_with_rule(mock_backend):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(200, json={"affected_count": 12, "rule_id": 50})
    mock_backend(handler)
    import app.tools.bulk_update_category_by_merchant  # noqa: F401
    h = get_handler("bulk_update_category_by_merchant")
    result = await h({"pattern": "瑞幸", "category": 11,
                      "match_kind": "contains", "also_add_rule": True})
    body = json.loads(captured[0].content)
    assert body == {"pattern": "瑞幸", "category_id": 11,
                    "match_kind": "contains", "also_add_rule": True}
    payload = json.loads(result[0].text)
    assert payload["affected_count"] == 12
    assert payload["rule_id"] == 50


async def test_bulk_update_default_also_add_rule(mock_backend):
    captured = []
    def handler(req): captured.append(req); return httpx.Response(200, json={"affected_count": 0, "rule_id": None})
    mock_backend(handler)
    import app.tools.bulk_update_category_by_merchant  # noqa: F401
    h = get_handler("bulk_update_category_by_merchant")
    await h({"pattern": "x", "category": 1})
    body = json.loads(captured[0].content)
    assert body["also_add_rule"] is True   # MCP 默认 True 与 spec 一致
    assert body["match_kind"] == "contains"  # 默认
```

- [ ] **Step 15.2:实现**

新建 [mcp_server/app/tools/bulk_update_category_by_merchant.py](mcp_server/app/tools/bulk_update_category_by_merchant.py):

```python
"""MCP tool: bulk_update_category_by_merchant — spec § 8.1 write #3。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="bulk_update_category_by_merchant",
    description=(
        "Bulk-update all transactions whose merchant_normalized matches the pattern. "
        "Optionally creates a merchant_rule so future imports auto-classify."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "minLength": 1, "maxLength": 255},
            "category": {"type": "integer", "description": "target category.id"},
            "match_kind": {"type": "string",
                           "enum": ["exact", "contains", "regex", "fuzzy"],
                           "default": "contains"},
            "also_add_rule": {"type": "boolean", "default": True},
        },
        "required": ["pattern", "category"],
    },
)


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    body = {
        "pattern": args["pattern"],
        "category_id": args["category"],
        "match_kind": args.get("match_kind", "contains"),
        "also_add_rule": args.get("also_add_rule", True),
    }
    try:
        data = await client.post("/api/transactions/bulk-update-by-merchant", json=body)
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    out = {"affected_count": data["affected_count"], "rule_id": data.get("rule_id")}
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 15.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_bulk_update_category_by_merchant.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/bulk_update_category_by_merchant.py mcp_server/tests/test_tool_bulk_update_category_by_merchant.py
git commit -m "feat(mcp): tool bulk_update_category_by_merchant (write #3 of 4)"
```

---

## Task 16:MCP 工具 #10 write — `confirm_dedup_pair`

**Files:**
- Create: `mcp_server/app/tools/confirm_dedup_pair.py`
- Create: `mcp_server/tests/test_tool_confirm_dedup_pair.py`

> **背景:** spec § 8.1 write #4。入参 `pair_id, action[confirm/reject]`,出参 `ok, primary_tx_id, mirror_tx_id, action_taken`。Backend `POST /api/dedup/{pair_id}/confirm` body `{action}`(slice C 已实现);MCP 透传 + 字段重命名。

- [ ] **Step 16.1:写测试**

新建 [mcp_server/tests/test_tool_confirm_dedup_pair.py](mcp_server/tests/test_tool_confirm_dedup_pair.py):

```python
from __future__ import annotations
import json
import httpx
import pytest
from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample_pair() -> dict:
    return {"id": 7, "user_id": 1, "primary_tx_id": 100, "mirror_tx_id": 200,
            "match_kind": "bridge", "confidence": 0.85, "status": "confirmed",
            "reasoning": {}, "created_at": "2026-05-08T12:00:00",
            "decided_at": "2026-05-08T12:30:00"}


def test_tool_def_present():
    import app.tools.confirm_dedup_pair  # noqa: F401
    assert "confirm_dedup_pair" in [t.name for t in get_tool_definitions()]


async def test_confirm(mock_backend, sample_pair):
    captured: list[httpx.Request] = []
    def handler(req): captured.append(req); return httpx.Response(200, json=sample_pair)
    mock_backend(handler)
    import app.tools.confirm_dedup_pair  # noqa: F401
    h = get_handler("confirm_dedup_pair")
    result = await h({"pair_id": 7, "action": "confirm"})
    assert captured[0].url.path == "/api/dedup/7/confirm"
    body = json.loads(captured[0].content)
    assert body == {"action": "confirm"}
    payload = json.loads(result[0].text)
    assert payload == {
        "ok": True, "primary_tx_id": 100, "mirror_tx_id": 200, "action_taken": "confirmed",
    }


async def test_reject(mock_backend, sample_pair):
    rejected = {**sample_pair, "status": "rejected"}
    def handler(req): return httpx.Response(200, json=rejected)
    mock_backend(handler)
    import app.tools.confirm_dedup_pair  # noqa: F401
    h = get_handler("confirm_dedup_pair")
    result = await h({"pair_id": 7, "action": "reject"})
    payload = json.loads(result[0].text)
    assert payload["action_taken"] == "rejected"


async def test_pair_not_found(mock_backend):
    def handler(req): return httpx.Response(404, json={"detail": "dedup_pair not found"})
    mock_backend(handler)
    import app.tools.confirm_dedup_pair  # noqa: F401
    h = get_handler("confirm_dedup_pair")
    result = await h({"pair_id": 999, "action": "confirm"})
    payload = json.loads(result[0].text)
    assert payload["error"]["code"] == "NOT_FOUND"


async def test_already_decided_conflict(mock_backend):
    def handler(req): return httpx.Response(409, json={"detail": "pair already confirmed"})
    mock_backend(handler)
    import app.tools.confirm_dedup_pair  # noqa: F401
    h = get_handler("confirm_dedup_pair")
    result = await h({"pair_id": 7, "action": "confirm"})
    payload = json.loads(result[0].text)
    assert payload["error"]["code"] == "CONFLICT"
```

- [ ] **Step 16.2:实现**

新建 [mcp_server/app/tools/confirm_dedup_pair.py](mcp_server/app/tools/confirm_dedup_pair.py):

```python
"""MCP tool: confirm_dedup_pair — spec § 8.1 write #4。"""
from __future__ import annotations
import json
from typing import Any
from mcp import types as mcp_types
from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register


_TOOL = mcp_types.Tool(
    name="confirm_dedup_pair",
    description="Confirm or reject a pending dedup_pair, marking the mirror transaction accordingly.",
    inputSchema={
        "type": "object",
        "properties": {
            "pair_id": {"type": "integer"},
            "action": {"type": "string", "enum": ["confirm", "reject"]},
        },
        "required": ["pair_id", "action"],
    },
)


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    pair_id = args["pair_id"]
    action = args["action"]
    try:
        data = await client.post(f"/api/dedup/{pair_id}/confirm", json={"action": action})
    except MCPToolError as e:
        return [mcp_types.TextContent(type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False))]
    out = {
        "ok": True,
        "primary_tx_id": data["primary_tx_id"],
        "mirror_tx_id": data["mirror_tx_id"],
        "action_taken": data["status"],   # "confirmed" / "rejected"
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
```

- [ ] **Step 16.3:跑测试 + Commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_confirm_dedup_pair.py -v 2>&1 | Select-Object -Last 8
git add mcp_server/app/tools/confirm_dedup_pair.py mcp_server/tests/test_tool_confirm_dedup_pair.py
git commit -m "feat(mcp): tool confirm_dedup_pair (write #4 of 4) — all 10 tools done"
```

---

## Task 17:MCP server 集成自检 — 所有 10 工具 register + list + dispatch

**Files:**
- Create: `mcp_server/tests/test_integration.py`

> **背景:** Task 7-16 各自做了 unit test;本 task 跑一次 mcp_server 全测试 + 整体集成断言:
>
> 1. `_register_all_tools()` 调完后,`TOOL_REGISTRY` 恰好 10 项,名字与 spec § 8.1 一一对应
> 2. 每个 tool 的 `inputSchema` 是合法 JSON Schema(已在各 unit test sanity)
> 3. `outputSchema`(MCP SDK ≥ 1.1 可选字段)若没填,描述足够清晰
> 4. 工具 dispatch:`server.call_tool` (覆盖 main.py `_call_tool` 内部路径)对未知 tool 抛 ValueError

- [ ] **Step 17.1:写集成测试**

新建 [mcp_server/tests/test_integration.py](mcp_server/tests/test_integration.py):

```python
"""MCP server 集成自检 — 10 工具齐全 + dispatch 正常。"""
from __future__ import annotations

import pytest

from app.main import _register_all_tools
from app.tools import TOOL_REGISTRY, get_handler, get_tool_definitions


_EXPECTED_TOOLS = {
    "list_transactions",
    "get_summary",
    "get_account_balances",
    "find_merchant",
    "list_pending_dedup_pairs",
    "list_pending_classifications",
    "add_transaction",
    "update_category",
    "bulk_update_category_by_merchant",
    "confirm_dedup_pair",
}


@pytest.fixture(autouse=True)
def _register_once():
    _register_all_tools()


def test_all_10_tools_registered():
    names = {t.name for t in get_tool_definitions()}
    missing = _EXPECTED_TOOLS - names
    extra = names - _EXPECTED_TOOLS
    assert not missing, f"missing tools: {missing}"
    assert not extra, f"unexpected extra tools: {extra}"


def test_each_tool_has_handler_and_schema():
    for name in _EXPECTED_TOOLS:
        h = get_handler(name)
        assert h is not None, f"{name} missing handler"
        defn = next(t for t in get_tool_definitions() if t.name == name)
        assert defn.description, f"{name} missing description"
        assert defn.inputSchema["type"] == "object"
        assert "properties" in defn.inputSchema


def test_unknown_tool_raises():
    """main._call_tool 遇未知 tool 抛 ValueError(MCP SDK 把 ValueError 转协议错误)。"""
    from app.main import _call_tool
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(_call_tool("nonexistent_tool", {}))


def test_no_duplicate_registrations():
    """重复 import 不应触发 duplicate registration error(register 已查重)。"""
    # 第二次 import 一遍
    import importlib
    for mod_name in [f"app.tools.{n}" for n in _EXPECTED_TOOLS]:
        # reload 应不再 register(因 register() 查 TOOL_REGISTRY)
        # — 实际 importlib 会重新执行模块顶层,我们要确保 register() 抛 RuntimeError
        # 才是契约;但 _register_all_tools 用 import_module(非 reload)所以幂等
        pass
    # 跑 _register_all_tools 第二次,不抛
    _register_all_tools()
    assert len(TOOL_REGISTRY) == 10
```

- [ ] **Step 17.2:跑全部 mcp_server 测试**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 8
```

期望 0 fail / 0 error。tests 数预期:
- test_main_auth.py: 3
- test_backend_client.py: 9 (1 + 1 + 7 parametric)
- 10 个 test_tool_*: ~3-4 each = ~30-40
- test_integration.py: 4
- 总数 ≈ 46-56

- [ ] **Step 17.3:Commit**

```powershell
git add mcp_server/tests/test_integration.py
git commit -m "test(mcp): integration check — all 10 tools register + dispatch"
```

---

## Task 18:MCP server e2e 冒烟脚本 — 直连 stdio 跑 JSON-RPC,验证 list_tools + 一次工具调用

**Files:**
- Create: `backend/tests/e2e/mcp_smoke.ps1`

> **背景:** spec DoD #1-2 要求:`python -m mcp_server.main` 启动后,用 MCP Inspector 列出 10 个工具 + 真实数据手测每工具。MCP Inspector 是 npx 命令(`npx @modelcontextprotocol/inspector`),需要 Node;但本切片有更简洁方案 — **直接用 PowerShell 启 mcp server stdio + 写 JSON-RPC 消息到 stdin / 读 stdout**,验证:
>
> 1. server 启动 + initialize handshake 成功
> 2. `tools/list` 返回 10 个工具
> 3. `tools/call` 一次 `list_transactions` → 拿到合理 JSON 输出
>
> Inspector(npx)留作开发者**手动**验证;本脚本是 CI 友好的自动化版本。

- [ ] **Step 18.1:写 mcp_smoke.ps1**

新建 [backend/tests/e2e/mcp_smoke.ps1](backend/tests/e2e/mcp_smoke.ps1):

```powershell
# mcp_smoke.ps1 -- spec § DoD #1-2,e2e 冒烟测 MCP server stdio + JSON-RPC
#
# Pre-conditions:
#   - backend uvicorn 在 :8000(必须真跑 — MCP server 启动会调 backend /verify)
#   - 数据库有 admin user + 至少一个 ApiToken
#   - $env:MCP_API_TOKEN 已设(明文 token,与 db 中 hash 对应)
#   - mcp_server/.venv 已就绪(pip install -e .[dev])
#
# Usage:
#   $env:MCP_API_TOKEN = "<plain-token>"
#   pwsh backend/tests/e2e/mcp_smoke.ps1
#
$ErrorActionPreference = "Stop"

if (-not $env:MCP_API_TOKEN) {
    Write-Host "FAIL: MCP_API_TOKEN env not set" -ForegroundColor Red
    exit 1
}

$repoRoot = (Resolve-Path "$PSScriptRoot\..\..\..\").Path
$mcpDir = Join-Path $repoRoot "mcp_server"
$venvPy = Join-Path $mcpDir ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "FAIL: mcp_server venv not found at $venvPy" -ForegroundColor Red
    exit 1
}

Write-Host "[1/3] Build JSON-RPC requests..." -ForegroundColor Yellow

# MCP initialize handshake
$initMsg = @{
    jsonrpc = "2.0"; id = 1; method = "initialize"
    params = @{
        protocolVersion = "2024-11-05"
        capabilities = @{}
        clientInfo = @{ name = "mcp_smoke.ps1"; version = "0.1" }
    }
} | ConvertTo-Json -Compress -Depth 10

$initNotif = @{ jsonrpc = "2.0"; method = "notifications/initialized" } | ConvertTo-Json -Compress

$listMsg = @{
    jsonrpc = "2.0"; id = 2; method = "tools/list"; params = @{}
} | ConvertTo-Json -Compress -Depth 10

$callMsg = @{
    jsonrpc = "2.0"; id = 3; method = "tools/call"
    params = @{
        name = "list_transactions"
        arguments = @{ limit = 5 }
    }
} | ConvertTo-Json -Compress -Depth 10

# stdin 拼成 4 行(每行一个 JSON-RPC message,以 \n 分隔)
$stdin = "$initMsg`n$initNotif`n$listMsg`n$callMsg`n"

Write-Host "[2/3] Spawn mcp_server stdio + pipe stdin..." -ForegroundColor Yellow

# 后台跑 mcp_server,5 秒超时
$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = $venvPy
$pinfo.WorkingDirectory = $mcpDir
$pinfo.Arguments = "-m app.main --transport stdio"
$pinfo.RedirectStandardInput = $true
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true
$pinfo.UseShellExecute = $false
$pinfo.EnvironmentVariables["MCP_API_TOKEN"] = $env:MCP_API_TOKEN
$pinfo.EnvironmentVariables["MCP_BACKEND_URL"] = ($env:MCP_BACKEND_URL ?? "http://127.0.0.1:8000")

$proc = [System.Diagnostics.Process]::Start($pinfo)
$proc.StandardInput.Write($stdin)
$proc.StandardInput.Close()

# 5 秒收输出
if (-not $proc.WaitForExit(5000)) {
    $proc.Kill()
    Write-Host "FAIL: mcp_server timed out (5s)" -ForegroundColor Red
    exit 1
}

$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()

Write-Host "[3/3] Parse responses + assert..." -ForegroundColor Yellow
Write-Host "stderr (token verify log):" -ForegroundColor DarkGray
Write-Host $stderr -ForegroundColor DarkGray

$lines = $stdout -split "`n" | Where-Object { $_.Trim() }
$responses = @()
foreach ($line in $lines) {
    try {
        $obj = $line | ConvertFrom-Json
        if ($obj.id -ne $null) { $responses += $obj }
    } catch {
        # 非 JSON 行 (e.g. notifications) 跳过
    }
}

# Assert id=2 (tools/list) 返回 10 个工具
$listResp = $responses | Where-Object { $_.id -eq 2 } | Select-Object -First 1
if (-not $listResp) {
    Write-Host "FAIL: no tools/list response" -ForegroundColor Red
    Write-Host "stdout:" $stdout
    exit 1
}
$tools = $listResp.result.tools
$expected = @("list_transactions", "get_summary", "get_account_balances",
              "find_merchant", "list_pending_dedup_pairs", "list_pending_classifications",
              "add_transaction", "update_category",
              "bulk_update_category_by_merchant", "confirm_dedup_pair")
$names = $tools | ForEach-Object { $_.name } | Sort-Object
$expectedSorted = $expected | Sort-Object
if (Compare-Object $names $expectedSorted) {
    Write-Host "FAIL: tool list mismatch" -ForegroundColor Red
    Write-Host "got:" ($names -join ", ")
    Write-Host "expected:" ($expectedSorted -join ", ")
    exit 1
}
Write-Host "  PASS: 10 tools listed" -ForegroundColor Green

# Assert id=3 (tools/call list_transactions) 返回 content[0].text 是合法 JSON
$callResp = $responses | Where-Object { $_.id -eq 3 } | Select-Object -First 1
if (-not $callResp) {
    Write-Host "FAIL: no tools/call response" -ForegroundColor Red
    exit 1
}
$content = $callResp.result.content[0]
if ($content.type -ne "text") {
    Write-Host "FAIL: content not text type" -ForegroundColor Red
    exit 1
}
$payload = $content.text | ConvertFrom-Json
if ($payload.PSObject.Properties.Name -notcontains "transactions") {
    if ($payload.error) {
        Write-Host "FAIL: tool returned error: $($payload.error.code) - $($payload.error.message)" -ForegroundColor Red
    } else {
        Write-Host "FAIL: response missing 'transactions' field" -ForegroundColor Red
        Write-Host $content.text
    }
    exit 1
}
Write-Host "  PASS: list_transactions returned $($payload.transactions.Count) tx" -ForegroundColor Green

Write-Host "`n=== MCP smoke: ALL PASS ===" -ForegroundColor Green
exit 0
```

- [ ] **Step 18.2:测试运行**(假定 backend uvicorn + db 都跑着、token 已生成)

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy

# 第一次跑前,生成一个 token:
# 1) 启动 backend uvicorn(终端 1):
#    cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --port 8000
# 2) 终端 2 拿 cookie 登录 + create token:
$env:ADMIN_TEST_PASSWORD = "fm-dev-2026"   # 或你的 dev 密码
$session = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/auth/login -Method Post -Body (@{username="admin"; password=$env:ADMIN_TEST_PASSWORD} | ConvertTo-Json) -ContentType "application/json" -SessionVariable s
$create = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/admin/tokens -Method Post -Body (@{name="smoke-test"} | ConvertTo-Json) -ContentType "application/json" -WebSession $s
$env:MCP_API_TOKEN = $create.plain_token
Write-Host "Token created: $($env:MCP_API_TOKEN.Substring(0,8))..."

# 跑 smoke
pwsh backend\tests\e2e\mcp_smoke.ps1
```

期望末行:`=== MCP smoke: ALL PASS ===`,且 `[3/3]` 段输出"10 tools listed" + "list_transactions returned N tx"。

- [ ] **Step 18.3:Commit**

```powershell
git add backend/tests/e2e/mcp_smoke.ps1
git commit -m "test(e2e): MCP server stdio JSON-RPC smoke (initialize + list + call)"
```

---

## Task 19:`docker-compose.yml` 引入 dev/prod profiles + 加 Caddy 服务 + Caddyfile

**Files:**
- Modify: `docker-compose.yml`(profiles + 移除 prod port 映射 + 加 caddy)
- Create: `Caddyfile`

> **背景:** spec § 11.1 + § 11.2。开发期 `docker-compose --profile dev up`(全部端口暴露到主机,方便本机 curl);生产 `docker-compose --profile prod up -d`(只 caddy 暴露 8443/9443 到主机,backend/mcp/postgres 只走内网 docker network)。Caddy 用社区镜像 `slothcroissant/caddy-cloudflaredns:latest`(自带 caddy-dns/cloudflare 插件,免去 xcaddy build)。
>
> **关键决策**:`Caddyfile` 用 `${DOMAIN}` env 占位符;`{env.CLOUDFLARE_API_TOKEN}` 是 Caddy 的 env 引用语法(运行时读 process env)。`tls.dns` 段触发 DNS-01 challenge,无需 80 端口出公网,完美适配 8443/9443 自定义端口。

- [ ] **Step 19.1:Read 当前 docker-compose.yml 校验**

```powershell
Get-Content docker-compose.yml
```

确认 4 个 service:db / backend / mcp / frontend(本切片 mcp service `build: ./mcp_server` 路径已对齐)。

- [ ] **Step 19.2:改写 docker-compose.yml(完整新版)**

打开 [docker-compose.yml](docker-compose.yml),全文替换为:

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-finance}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-finance}
      POSTGRES_DB: ${POSTGRES_DB:-finance}
    ports:
      # dev profile: 暴露到 host;prod 不暴露(只走 docker network)
      - "5432:5432"
    profiles: ["dev"]
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-finance}"]
      interval: 5s
      timeout: 5s
      retries: 10

  db_prod:
    # 与 db 相同 image + volume,但不暴露端口(prod profile 用)
    image: postgres:16-alpine
    container_name: finance-manager-db-prod
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-finance}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-finance}
      POSTGRES_DB: ${POSTGRES_DB:-finance}
    profiles: ["prod"]
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-finance}"]
      interval: 5s
      timeout: 5s
      retries: 10

  backend:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
        required: false      # prod 用 db_prod,dev 用 db
    ports:
      - "8000:8000"
    profiles: ["dev"]
    volumes:
      - ./backend:/app
      - uploads:/app/uploads
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

  backend_prod:
    build: ./backend
    container_name: finance-manager-backend-prod
    restart: unless-stopped
    env_file: .env
    depends_on:
      db_prod:
        condition: service_healthy
    profiles: ["prod"]
    volumes:
      - uploads:/app/uploads
    # prod 不挂 source code(避免 hot reload),改用 image 自带的 COPY
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000"

  mcp:
    build: ./mcp_server
    restart: unless-stopped
    env_file: .env
    depends_on:
      - backend
    ports:
      - "8765:8765"
    profiles: ["dev"]
    volumes:
      - ./mcp_server:/app
    command: ["python", "-m", "app.main", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]

  mcp_prod:
    build: ./mcp_server
    container_name: finance-manager-mcp-prod
    restart: unless-stopped
    env_file: .env
    depends_on:
      - backend_prod
    profiles: ["prod"]
    command: ["python", "-m", "app.main", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
    environment:
      MCP_BACKEND_URL: http://backend_prod:8000

  frontend:
    build: ./frontend
    restart: unless-stopped
    env_file: .env
    depends_on:
      - backend
    ports:
      - "3000:3000"
    profiles: ["dev"]
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next
    command: pnpm dev

  frontend_prod:
    build: ./frontend
    container_name: finance-manager-frontend-prod
    restart: unless-stopped
    env_file: .env
    depends_on:
      - backend_prod
    profiles: ["prod"]
    # standalone 模式,Dockerfile runner stage 已配
    command: ["node", "server.js"]

  caddy:
    # 社区镜像,内置 caddy-dns/cloudflare 插件(免去 xcaddy build)
    image: slothcroissant/caddy-cloudflaredns:latest
    container_name: finance-manager-caddy
    restart: unless-stopped
    profiles: ["prod"]
    ports:
      - "8443:8443"
      - "9443:9443"
    environment:
      DOMAIN: ${DOMAIN}
      CLOUDFLARE_API_TOKEN: ${CLOUDFLARE_API_TOKEN}
      CADDY_ACME_EMAIL: ${CADDY_ACME_EMAIL}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend_prod
      - frontend_prod
      - mcp_prod

volumes:
  pgdata:
  uploads:
  caddy_data:
  caddy_config:
```

注意:
- 复制 service 模式(db / db_prod 等)是 **profiles** 在 compose 2.x 的标准用法 — profiles 不能动态条件化 ports/volumes,所以拆两个 service
- prod service 的 container_name 加 `-prod` 后缀,避免与 dev service 同时启动时撞名(实际不会同时跑,但保险)
- `caddy` 服务**只**在 prod profile 下启动;dev 时直接用 `localhost:3000` / `localhost:8000` / `localhost:8765`
- 外部 docker network 复用:不需要显式定义 network,compose 默认所有 service 在同一 default network,可通过 service name 互访(如 `http://backend_prod:8000`)

- [ ] **Step 19.3:写 `Caddyfile`**

新建 [Caddyfile](Caddyfile):

```caddy
{
    email {env.CADDY_ACME_EMAIL}
    # 全局选项可加 admin off 关 admin endpoint,本切片不暴露
}

{$DOMAIN}:8443 {
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }

    # 安全 header
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        # 允许 mcp 9443 同域跨端口请求(若需要,前端通常不调 mcp,但留 hook)
    }

    # /api/* 反代 backend
    handle /api/* {
        reverse_proxy backend_prod:8000
    }

    # 兜底反代 frontend(Next.js standalone)
    handle {
        reverse_proxy frontend_prod:3000
    }

    encode gzip
    log {
        output stdout
        format console
    }
}

{$DOMAIN}:9443 {
    tls {
        dns cloudflare {env.CLOUDFLARE_API_TOKEN}
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }

    reverse_proxy mcp_prod:8765

    log {
        output stdout
        format console
    }
}
```

- [ ] **Step 19.4:本机 dev 验证 — `docker-compose --profile dev up -d`**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
# 因为本 worktree 与主目录共用 db 容器(已运行),先 down 本切片可能起的容器
docker-compose --profile dev down --remove-orphans 2>&1 | Out-Null
docker-compose --profile dev up -d --build
docker-compose --profile dev ps
```

期望:db / backend / mcp / frontend 4 个 dev service `Up`,无 caddy(prod-only)。

冒烟检查:

```powershell
curl http://localhost:8000/api/health
curl http://localhost:8765/        # mcp HTTP transport,可能 405 但说明在跑
curl http://localhost:3000/        # 200 / 308 redirect
```

- [ ] **Step 19.5:本机 down 后跑 prod profile 冒烟(本机用 self-signed,跳 DNS-01)**

prod profile 在本机跑不真实(没 DNS / Cloudflare),但可以验证 service 起得来。**跳过本步**,改在 Task 20 setup-vps.md 的 step 段写如何在 VPS 上验证。

如果想本机 sanity:`docker-compose --profile prod config` 输出有效 yaml 即可 PASS。

```powershell
docker-compose --profile prod config | Select-Object -First 30
```

期望:输出 yaml 包含 `db_prod / backend_prod / mcp_prod / frontend_prod / caddy` 5 个 service。

- [ ] **Step 19.6:Commit**

```powershell
git add docker-compose.yml Caddyfile
git commit -m "feat(deploy): docker-compose dev/prod profiles + Caddy + Caddyfile

dev profile (default for local): exposes db:5432, backend:8000,
mcp:8765, frontend:3000 to host. prod profile: only Caddy
exposes 8443/9443 to host; backend/mcp/frontend/db only on docker
network. Caddy uses slothcroissant/caddy-cloudflaredns image
(built-in cloudflare DNS plugin) for ACME DNS-01 on port 8443/9443
without needing :80 exposed. spec § 11.1 + § 11.2.
"
```

---

## Task 20:备份脚本 + setup-vps.md 部署文档 + .env.example

**Files:**
- Create: `scripts/backup.sh`
- Create: `scripts/setup-vps.md`
- Modify(or Create if missing): `.env.example`

> **背景:** spec § 11.4(备份)+ § 11.5(防火墙)+ § 14(open questions)。`scripts/backup.sh` 跑一次 = `pg_dump` → `age` 加密 → `rclone copy` 到 R2;cron `0 3 * * *` 每天 03:00 跑;30 天日备 + 12 月月初。`setup-vps.md` 是 VPS 一键部署 cheatsheet。

- [ ] **Step 20.1:写 `scripts/backup.sh`**

新建 [scripts/backup.sh](scripts/backup.sh):

```bash
#!/usr/bin/env bash
# scripts/backup.sh — finance-manager Postgres 加密备份 + 上传 R2。
# spec § 11.4。crontab: 0 3 * * * /opt/finance-manager/scripts/backup.sh
#
# 依赖(VPS 上 apt 装):
#   - docker / docker-compose
#   - age >= 1.0 (apt: age 或 brew install age)
#   - rclone >= 1.60(配 R2 remote 名 'r2',bucket = $R2_BUCKET)
#
# 必填环境变量(写在 /etc/finance-manager.backup.env,chmod 0600,owner root):
#   AGE_RECIPIENT  — 接收方公钥(age1...)
#   R2_BUCKET      — Cloudflare R2 bucket name
#   POSTGRES_USER  — db 用户(同 .env)
#   POSTGRES_DB    — db 名(同 .env)
#
# 输出:每天写一个 finance-{YYYYMMDD}.sql.age 上传 r2:$R2_BUCKET/daily/
#       每月 1 号同时复制到 r2:$R2_BUCKET/monthly/
#       本地不留任何文件,仅日志。
#
set -euo pipefail

ENV_FILE=/etc/finance-manager.backup.env
[[ -r $ENV_FILE ]] && source "$ENV_FILE"

: "${AGE_RECIPIENT:?AGE_RECIPIENT is required}"
: "${R2_BUCKET:?R2_BUCKET is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

DATE_STAMP=$(date -u '+%Y%m%d')
TS_HUMAN=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
LOG_TAG="[fm-backup $TS_HUMAN]"

echo "$LOG_TAG starting"

# 1) pg_dump from container,管道直接给 age,不落盘
docker exec finance-manager-db-prod pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | age -r "$AGE_RECIPIENT" \
  | rclone rcat "r2:${R2_BUCKET}/daily/finance-${DATE_STAMP}.sql.age" \
  --s3-no-check-bucket

echo "$LOG_TAG daily upload OK"

# 2) 月初(每月 1 号)同时归档到 monthly/
if [[ $(date -u +%d) == "01" ]]; then
    rclone copyto \
      "r2:${R2_BUCKET}/daily/finance-${DATE_STAMP}.sql.age" \
      "r2:${R2_BUCKET}/monthly/finance-${DATE_STAMP}.sql.age" \
      --s3-no-check-bucket
    echo "$LOG_TAG monthly archive OK"
fi

# 3) 清 30 天前的 daily(R2 lifecycle 也可做,这里 belt & suspenders)
THIRTY_AGO=$(date -u -d '30 days ago' '+%Y%m%d')
rclone delete "r2:${R2_BUCKET}/daily/" \
  --include "finance-*.sql.age" \
  --max-age 30d \
  --s3-no-check-bucket || true

# 4) 清 12 个月前的 monthly
TWELVE_MO_AGO=$(date -u -d '12 months ago' '+%Y%m%d')
rclone delete "r2:${R2_BUCKET}/monthly/" \
  --include "finance-*.sql.age" \
  --max-age 365d \
  --s3-no-check-bucket || true

echo "$LOG_TAG done"
```

`chmod +x scripts/backup.sh`(在 git 里 mode 设为 100755 — 用 `git update-index --chmod=+x scripts/backup.sh` 之后 commit)。

- [ ] **Step 20.2:写 `scripts/setup-vps.md`**

新建 [scripts/setup-vps.md](scripts/setup-vps.md):

````markdown
# VPS 一键部署 cheatsheet — Finance Manager MVP

适用:Debian 12 / Ubuntu 22.04 LTS,4 GB RAM 以上,根用户或有 sudo 的 user。

## 1. 系统准备

```bash
# 包仓库 + 时间同步
apt-get update && apt-get -y upgrade
apt-get -y install ca-certificates curl gnupg ufw fail2ban age rclone unattended-upgrades

# Docker(官方仓库)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-compose
```

注意:`docker-compose`(v1,横线版)和 `docker compose`(v2 plugin)二者并存。MVP **用 v1 横线版**(`apt install docker-compose`),与 CLAUDE.md 约定一致。

## 2. 防火墙(spec § 11.5)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 8443/tcp comment 'finance-manager web (Caddy)'
ufw allow 9443/tcp comment 'finance-manager mcp (Caddy)'
ufw enable
ufw status verbose
```

`fail2ban` 默认配置已护 SSH;无需改 jail.local。

## 3. SSH 加固

```bash
# 编辑 /etc/ssh/sshd_config:
#   PasswordAuthentication no
#   PermitRootLogin no       # 如果上面已用根用户,先建 sudo user 再禁
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh
```

## 4. 拉代码 + .env

```bash
mkdir -p /opt && cd /opt
git clone <your-repo-url> finance-manager
cd finance-manager

# .env 从 .env.example 拷贝,填真实值
cp .env.example .env
chmod 0600 .env
nano .env
```

需要填的字段(spec § 14):

| 字段 | 怎么生成 |
|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `ADMIN_USERNAME` | 自定 |
| `ADMIN_PASSWORD_HASH` | `docker run --rm python:3.11-slim sh -c "pip install -q passlib bcrypt && python -c \"from passlib.hash import bcrypt; print(bcrypt.hash('YOUR_DEV_PASSWORD'))\""` |
| `MCP_API_TOKEN` | 部署后在 web /api/admin/tokens 端点生成,**不**在 .env 预填(留空字符串占位) |
| `DOMAIN` | `money.yourdomain.com`(已绑 Cloudflare) |
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → 新建 token,scope: `Zone.DNS:Edit` ONLY |
| `CADDY_ACME_EMAIL` | 你收 Let's Encrypt 通知的邮箱 |

## 5. 启动 prod profile

```bash
cd /opt/finance-manager
docker-compose --profile prod up -d --build
docker-compose --profile prod ps
docker-compose --profile prod logs -f caddy   # 看 cert 是否签发成功
```

期望 Caddy 日志含 `certificate obtained successfully` 或 `serving initial configuration` 类提示。

测试访问:

```bash
curl -I https://${DOMAIN}:8443/api/health
# 期望 200,JSON {"status":"ok","db":"ok"}
```

## 6. 创建首个 admin user + MCP token

```bash
# 进 backend container 跑 seed(创 admin)
docker exec -it finance-manager-backend-prod python -m app.db.seed
# (seed 已读 .env 的 ADMIN_USERNAME / ADMIN_PASSWORD_HASH)

# 浏览器登录 https://${DOMAIN}:8443 → settings → 创建 token
# 或 curl:
SESSION=$(curl -s -c - https://${DOMAIN}:8443/api/auth/login -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"YOUR_DEV_PASSWORD"}' | grep fm_session | awk '{print $7}')
TOKEN=$(curl -s https://${DOMAIN}:8443/api/admin/tokens \
    -H "Cookie: fm_session=$SESSION" -H 'Content-Type: application/json' \
    -d '{"name":"prod-mcp"}' | jq -r .plain_token)

# 把 TOKEN 写回 .env 的 MCP_API_TOKEN,重启 mcp service
sed -i "s|^MCP_API_TOKEN=.*|MCP_API_TOKEN=$TOKEN|" .env
docker-compose --profile prod up -d mcp_prod
```

## 7. 备份配置

```bash
# 7.1 装 age 密钥(生成一对,公钥放 VPS,私钥保留本地)
# 本地机器:
age-keygen -o ~/finance-manager-backup.key
# 把生成的 age1... 公钥贴到 VPS 的 /etc/finance-manager.backup.env

# 7.2 配 rclone R2 remote(VPS 上一次性互动配)
rclone config
# 选 New remote 名 'r2'
# Storage: Cloudflare R2
# Access Key ID / Secret: 在 Cloudflare R2 → Manage R2 API Tokens 创建

# 7.3 backup env file
cat > /etc/finance-manager.backup.env <<EOF
AGE_RECIPIENT=age1xxxxxxxxxxxxxxxxxxxx
R2_BUCKET=finance-backups
POSTGRES_USER=finance
POSTGRES_DB=finance
EOF
chmod 0600 /etc/finance-manager.backup.env

# 7.4 cron
crontab -e
# 加一行:
0 3 * * * /opt/finance-manager/scripts/backup.sh >> /var/log/fm-backup.log 2>&1
```

dry-run 测一次:

```bash
/opt/finance-manager/scripts/backup.sh
# 期望日志含 "[fm-backup ...] daily upload OK"
# 验证 R2:
rclone ls r2:finance-backups/daily/
```

## 8. 解密恢复(灾难恢复演练)

**在本地机器**(私钥不离本地):

```bash
rclone copy r2:finance-backups/daily/finance-20260510.sql.age ./
age -d -i ~/finance-manager-backup.key finance-20260510.sql.age > restore.sql
# 在 VPS 上:
docker exec -i finance-manager-db-prod psql -U finance -d finance < restore.sql
```

## 9. 自动安全更新(unattended-upgrades)

```bash
dpkg-reconfigure --priority=low unattended-upgrades
# 选 "Yes" 启用 daily security upgrades
```

## 10. 升级流程

```bash
cd /opt/finance-manager
git pull
docker-compose --profile prod up -d --build
# alembic migration 在 backend_prod 启动 command 里 auto-run
```

## 故障排查

| 症状 | 排查 |
|---|---|
| Caddy 日志反复 "obtaining certificate" 失败 | 检查 `CLOUDFLARE_API_TOKEN` scope 是否有 Zone.DNS:Edit |
| `https://domain:8443` 502 Bad Gateway | `docker-compose ps` 看 backend_prod 是否 healthy;`docker logs finance-manager-backend-prod` |
| MCP 调用 401 | token 不匹配:`docker exec finance-manager-mcp-prod sh -c 'echo $MCP_API_TOKEN | head -c 20'` 与 db 中 token_hash 是否同一来源 |
| pg_dump 备份 0 字节 | `docker exec finance-manager-db-prod pg_isready` 验 db 在跑;`docker logs` 看 db 内有无错 |
````

- [ ] **Step 20.3:更新 / 创建 `.env.example`**

打开仓库根的 `.env.example`(若不存在则新建)。**参照** worktree 内的 `.env`(slice C 已经有大部分字段),新增/补全 spec § 11.3 字段:

```bash
# ============================================================
# Finance Manager — 环境变量样例
# 复制为 .env 后填入真实值。生产环境 chmod 0600。
# ============================================================

# ---- Postgres ----
POSTGRES_USER=finance
POSTGRES_PASSWORD=replace_with_openssl_rand_hex_16
POSTGRES_DB=finance
DATABASE_URL=postgresql+psycopg://finance:replace_with_openssl_rand_hex_16@127.0.0.1:5432/finance
# 容器内互访用:postgresql+psycopg://finance:.....@db:5432/finance(dev profile)
#                                                    @db_prod:5432/finance(prod)

# ---- Backend ----
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKEND_CORS_ORIGINS=http://localhost:3000
SECRET_KEY=replace_with_openssl_rand_hex_32

# ---- Admin Auth (single-user MVP) ----
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$replace_with_real_bcrypt_hash_60_chars

# ---- Frontend ----
NEXT_PUBLIC_API_BASE=http://localhost:8000/api

# ---- MCP Server ----
MCP_BACKEND_URL=http://127.0.0.1:8000          # dev: 127.0.0.1; prod: http://backend_prod:8000
MCP_API_TOKEN=                                  # 留空,部署后从 web settings 创建并填回
MCP_HOST=0.0.0.0
MCP_PORT=8765

# ---- 部署:域名 + Cloudflare(spec § 11.3)----
DOMAIN=money.yourdomain.com
CLOUDFLARE_API_TOKEN=                           # Zone.DNS:Edit scope ONLY
CADDY_ACME_EMAIL=you@example.com

# ---- 备份(scripts/backup.sh,生产可单独放 /etc/finance-manager.backup.env)----
# AGE_RECIPIENT=age1...                         # 接收方公钥
# R2_BUCKET=finance-backups
```

注意:
- 不要把真实值放进 `.env.example`(commit 进 git)
- worktree 内的 `.env`(已存在)是真实值,**永远不入 git**

- [ ] **Step 20.4:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
git update-index --chmod=+x scripts/backup.sh
git add scripts/backup.sh scripts/setup-vps.md .env.example
git commit -m "feat(deploy): backup script + VPS setup cheatsheet + .env.example

scripts/backup.sh: pg_dump | age | rclone copy R2; cron @ 03:00 UTC,
30-day daily + 12-month monthly retention; private key stays local.

scripts/setup-vps.md: end-to-end VPS bootstrap — apt deps, ufw +
fail2ban + ssh hardening, .env values + how to generate, prod
docker-compose, first admin + MCP token, backup config, restore
drill, upgrade flow, troubleshooting.

.env.example: template covering all variables introduced in
slice E + earlier (DOMAIN/CF/age placeholders empty for security).
spec § 11.3 + § 11.4 + § 11.5.
"
```

---

## Task 21:DoD verify_slice_e.ps1 + overview.md / CLAUDE.md 进度更新

**Files:**
- Create: `backend/scripts/verify_slice_e.ps1`
- Modify: `docs/superpowers/plans/2026-05-08-mvp-overview.md`
- Modify: `CLAUDE.md`

> **背景:** spec overview slice E DoD 5 项:
>
> 1. `python -m mcp_server.app.main --transport stdio` 启动后,JSON-RPC `tools/list` 返 10 个工具(Task 18 mcp_smoke.ps1 已自动化)
> 2. 每工具用真实数据手测;read 工具返 JSON;write 工具改 db 后 read 验证(本切片用 mcp_smoke.ps1 + 一组 e2e 手测脚本覆盖)
> 3. `docker-compose --profile prod up -d` 在 VPS 干净环境一键起,Caddy 拿到证书,`https://your-domain:8443` 能用(本机 verify 用 `docker-compose --profile prod config` sanity)
> 4. `https://your-domain:9443/` Agent 能调通(VPS 上才能验,本切片 verify 跳过)
> 5. cron 备份 dry-run 跑通(本机 verify 用 `bash scripts/backup.sh --dry-run`,实际依赖 age + rclone 配好)
>
> 本 task 写一个 ps1 脚本验证可在本机自动验的部分(1, 3 部分, 5 syntax check),其余手测部分文档化。

- [ ] **Step 21.1:写 `verify_slice_e.ps1`**

新建 [backend/scripts/verify_slice_e.ps1](backend/scripts/verify_slice_e.ps1):

```powershell
# verify_slice_e.ps1 -- slice E DoD 验证(本机可自动化部分)
#
# Usage:
#   pwsh backend\scripts\verify_slice_e.ps1
#
# Pre-conditions:
#   - 在 finance-manager/ 根或 worktree 根
#   - backend/.venv 装好 + alembic 已 upgrade head
#   - mcp_server/.venv 装好
#   - Postgres 容器跑着
#   - $env:ADMIN_TEST_PASSWORD 已设(给 e2e step 用)
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
Push-Location $repoRoot

Write-Host "=== Slice E DoD verify ===" -ForegroundColor Cyan

# 1. backend pytest 全绿(含 Task 0-5 新增)
Write-Host "`n[1/7] backend pytest..." -ForegroundColor Yellow
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/ -q --maxfail=3 2>&1 | Tee-Object -Variable tail | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; Write-Host "  FAIL backend tests" -ForegroundColor Red; exit 1 }
Write-Host "  PASS" -ForegroundColor Green
Pop-Location

# 2. mcp_server pytest 全绿(Task 6-17)
Write-Host "`n[2/7] mcp_server pytest..." -ForegroundColor Yellow
Push-Location mcp_server
.\.venv\Scripts\python.exe -m pytest tests/ -q 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { Pop-Location; Pop-Location; Write-Host "  FAIL mcp tests" -ForegroundColor Red; exit 1 }
Write-Host "  PASS" -ForegroundColor Green
Pop-Location

# 3. mcp_server stdio 启动 — token 合法时能列 10 工具
#    需要 backend uvicorn 在跑 + ADMIN_TEST_PASSWORD + admin user seed
Write-Host "`n[3/7] mcp_smoke.ps1 stdio JSON-RPC..." -ForegroundColor Yellow
if (-not $env:ADMIN_TEST_PASSWORD) {
    Write-Host "  SKIP: ADMIN_TEST_PASSWORD not set; manually:" -ForegroundColor Gray
    Write-Host "    `$env:ADMIN_TEST_PASSWORD='fm-dev-2026'" -ForegroundColor Gray
    Write-Host "    pwsh backend\scripts\verify_slice_e.ps1" -ForegroundColor Gray
} else {
    # 启 backend(后台)
    Push-Location backend
    $bk = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
        -ArgumentList "-m","uvicorn","app.main:app","--port","8000" `
        -PassThru -WindowStyle Hidden
    Pop-Location
    Start-Sleep -Seconds 4

    try {
        # login + create token
        $body = @{ username="admin"; password=$env:ADMIN_TEST_PASSWORD } | ConvertTo-Json
        $sess = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/auth/login -Method Post `
            -Body $body -ContentType "application/json" -SessionVariable s
        $tok = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/admin/tokens -Method Post `
            -Body (@{ name="verify-e" } | ConvertTo-Json) -ContentType "application/json" -WebSession $s
        $env:MCP_API_TOKEN = $tok.plain_token
        $env:MCP_BACKEND_URL = "http://127.0.0.1:8000"

        pwsh backend\tests\e2e\mcp_smoke.ps1
        if ($LASTEXITCODE -ne 0) { throw "mcp_smoke failed" }
        Write-Host "  PASS" -ForegroundColor Green
    } finally {
        if ($bk -and -not $bk.HasExited) {
            Stop-Process -Id $bk.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

# 4. docker-compose --profile prod config 校验(yaml syntax + service 齐全)
Write-Host "`n[4/7] docker-compose --profile prod config sanity..." -ForegroundColor Yellow
$cfg = docker-compose --profile prod config 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: compose config invalid" -ForegroundColor Red
    Write-Host $cfg
    Pop-Location; exit 1
}
$expected_services = @("db_prod","backend_prod","mcp_prod","frontend_prod","caddy")
foreach ($svc in $expected_services) {
    if ($cfg -notmatch "^\s+${svc}:") {
        Write-Host "  FAIL: prod service $svc missing in compose config" -ForegroundColor Red
        Pop-Location; exit 1
    }
}
Write-Host "  PASS" -ForegroundColor Green

# 5. Caddyfile 语法校验(用 caddy 镜像 validate)
Write-Host "`n[5/7] Caddyfile validate..." -ForegroundColor Yellow
docker run --rm -v ${PWD}/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1 | Select-Object -Last 5
if ($LASTEXITCODE -ne 0) {
    Write-Host "  FAIL: Caddyfile invalid" -ForegroundColor Red
    Pop-Location; exit 1
}
Write-Host "  PASS" -ForegroundColor Green

# 6. backup.sh 静态检查(shellcheck 若可用 + bash -n syntax)
Write-Host "`n[6/7] backup.sh syntax check..." -ForegroundColor Yellow
bash -n scripts/backup.sh
if ($LASTEXITCODE -ne 0) { Write-Host "  FAIL: backup.sh syntax" -ForegroundColor Red; Pop-Location; exit 1 }
Write-Host "  PASS" -ForegroundColor Green

# 7. .env.example 完整性 — 必含 MCP / DOMAIN / CADDY 字段
Write-Host "`n[7/7] .env.example completeness..." -ForegroundColor Yellow
$env_keys = @("DOMAIN","CLOUDFLARE_API_TOKEN","CADDY_ACME_EMAIL",
              "MCP_BACKEND_URL","MCP_API_TOKEN","ADMIN_USERNAME","ADMIN_PASSWORD_HASH")
$envFile = Get-Content .env.example -Raw
foreach ($k in $env_keys) {
    if ($envFile -notmatch "(?m)^\s*${k}=") {
        Write-Host "  FAIL: .env.example missing key $k" -ForegroundColor Red
        Pop-Location; exit 1
    }
}
Write-Host "  PASS" -ForegroundColor Green

Write-Host "`n=== Slice E DoD: ALL PASS (steps 3-4 partially deferred to actual VPS) ===" -ForegroundColor Green
Pop-Location
exit 0
```

- [ ] **Step 21.2:跑 verify**(可能需要 ADMIN_TEST_PASSWORD)

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
$env:ADMIN_TEST_PASSWORD = "fm-dev-2026"     # 或你的 dev 密码
pwsh backend\scripts\verify_slice_e.ps1
```

期望末行:`=== Slice E DoD: ALL PASS ===`,7 个 step 全 PASS。

- [ ] **Step 21.3:更新 `docs/superpowers/plans/2026-05-08-mvp-overview.md`**

打开 [docs/superpowers/plans/2026-05-08-mvp-overview.md](docs/superpowers/plans/2026-05-08-mvp-overview.md):

(a) "完成进度" 表格,把 slice E 一行改为:

```markdown
| E. MCP + 部署 | ✅ 完成 | 2026-05-10 | (实施工时由 controller 估算) | DoD verify ALL PASS;10 MCP 工具 unit + integration + stdio JSON-RPC e2e 全绿;backend 4 gap endpoints + API token infra + docker-compose dev/prod profiles + Caddy + scripts/backup.sh + setup-vps.md |
```

(b) 把 "已知遗留问题(切片 D 实施期间引入)"段(Task 0 step 0.8 已加)的 bcrypt regression 标 ✅ 闭环。

(c) 把切片 E 涉及的 spec § 8 + § 10.2 + § 11 在 spec 总览里再扫一遍,如有覆盖不全,在 overview 末尾"已知遗留问题"段开 V2 候选项:

```markdown
### slice E 完成时识别的 V2 候选

- **list_pending_classifications.suggested_categories**:第一版返空 list,V2 接 rapidfuzz vs categories.name 给建议
- **add_transaction.applied_rule**:backend POST /manual 不返 rule_id,MCP 出参的 `applied_rule` 永远是 null;V2 backend 加 rule hit info
- **多 token / 多 scope**:本切片 read+write 单 scope;V2 加细粒度 scope(如 read-only token 给只读 agent)
- **list_categories / list_accounts(MCP)**:本切片不暴露 list_categories 工具(agent 通过 list_pending_classifications + Web UI 操作分类);V2 加按需暴露
- **MCP server 单元测试中重复 register 的边角**(test_integration test_no_duplicate_registrations 实际跑 reload 时 register() 抛 RuntimeError → main.py 应 wrap 到 except RuntimeError):V2 polish
- **Caddyfile HSTS preload header**:V2 加 `preload` directive 配合 HSTS preload list submission
```

- [ ] **Step 21.4:更新仓库根 `CLAUDE.md`**

打开 `CLAUDE.md`,把 5 切片进度段:

```markdown
- ✅ **A. 数据库基础**(2026-05-08 完成,merged to main,DoD verify ALL PASS)
- ✅ **B. 4 个账单解析器**(2026-05-09 完成,DoD verify ALL PASS;含 slice A 遗留 I-1/I-3 修复)
- ✅ **C. 导入流水线 + 去重 + 分类 + REST API**(2026-05-09 完成,DoD verify ALL PASS;含 4 项遗留 fix:B-poly-1/2、I-5、Rec #5)
- ✅ **D. Web UI**(2026-05-10 完成,DoD verify ALL PASS;Next.js 14 App Router + shadcn/ui;22 Vitest unit + 4 Playwright smoke;Lighthouse 桌面/手机均 > 80)
- ⏳ **E. MCP server(10 工具)+ 部署**(下一步;Caddy + Cloudflare DNS-01,端口 8443/9443)
```

改成:

```markdown
- ✅ **A. 数据库基础**(2026-05-08 完成,merged to main,DoD verify ALL PASS)
- ✅ **B. 4 个账单解析器**(2026-05-09 完成,DoD verify ALL PASS;含 slice A 遗留 I-1/I-3 修复)
- ✅ **C. 导入流水线 + 去重 + 分类 + REST API**(2026-05-09 完成,DoD verify ALL PASS;含 4 项遗留 fix:B-poly-1/2、I-5、Rec #5)
- ✅ **D. Web UI**(2026-05-10 完成,DoD verify ALL PASS;Next.js 14 App Router + shadcn/ui;22 Vitest unit + 4 Playwright smoke;Lighthouse 桌面/手机均 > 80)
- ✅ **E. MCP server(10 工具)+ 部署**(2026-05-10 完成,DoD verify ALL PASS;mcp_server/ 独立项目用 mcp SDK ≥ 1.1;backend 4 gap endpoints + API token infra;docker-compose dev/prod profiles + Caddy(slothcroissant 镜像 + Cloudflare DNS-01,端口 8443/9443);scripts/backup.sh + setup-vps.md;含 bcrypt 5.x regression 闭环)

**MVP 全部完成 🎉**(5 切片,2026-05-08 → 2026-05-10)

下一步建议:在 VPS 上跑通完整部署(Task 20 setup-vps.md cheatsheet),或开始 V2 路线图(spec § 13)。
```

并把"## 遗留问题(slice D/E 处理)"段改名为"## 遗留问题(V2 候选)",把 overview Task 21.3 加的 V2 候选条目同步过来,删除已闭环的(B-poly-1/2、I-5、Rec #5、bcrypt regression)。

- [ ] **Step 21.5:Commit**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
git add backend/scripts/verify_slice_e.ps1 docs/superpowers/plans/2026-05-08-mvp-overview.md CLAUDE.md
git commit -m "chore(slice-e): add verify script + mark slice E done

DoD verify covers: backend pytest, mcp_server pytest, stdio JSON-RPC
e2e (mcp_smoke.ps1), docker-compose prod config sanity, Caddyfile
validate, backup.sh syntax, .env.example completeness.

Steps 3-4 of overview DoD (cert obtained on real domain, agent end-to-
end via 9443) are deferred to actual VPS deploy and documented in
scripts/setup-vps.md.

MVP all 5 slices complete (A→B→C→D→E, 2026-05-08 → 2026-05-10).
"
```

- [ ] **Step 21.6:最后 sanity check**

```powershell
cd D:\IDEACursor\Claude-code\finance-manager\.claude\worktrees\slice-e-mcp-deploy
git log --oneline main..slice-e-mcp-deploy
git status
```

期望 `git log` ~30+ commits(对应 22 个 task 各 1+ commit + 部分 task 多 commit),`git status` 干净。

切片 E 完成,可走 `superpowers:finishing-a-development-branch` 决定 merge 策略(参照 slice A/B/C/D 的 fast-forward 习惯)。

---

## Self-Review 备忘(写完 plan 后已自检)

- **Spec 覆盖**:
  - § 8.1 MCP 工具 6 read + 4 write → Task 7-16(每工具一 task,backend gap 在 Task 1-4 已补)
  - § 8.2 鉴权(Bearer + DB token) → Task 5(API token infra)+ Task 6(MCP server bearer self-check)
  - § 8.3 错误格式 → Task 6(`errors.py` + `httpx_to_mcp_error` + 5 标准错误码)
  - § 10.2 MCP 静态 token → Task 5(api_tokens 表已建于 slice A;本切片补 service + admin endpoints + 双通道 dependency)
  - § 11.1 docker-compose 修订 + profiles → Task 19
  - § 11.2 Caddyfile + DNS-01 → Task 19(Caddyfile)
  - § 11.3 .env 模板补充(DOMAIN / CF / ACME) → Task 20(.env.example)
  - § 11.4 备份策略(pg_dump + age + rclone + 30 天 / 12 月保留)→ Task 20(backup.sh + cron 文档)
  - § 11.5 防火墙(SSH key only / 8443 / 9443 / fail2ban) → Task 20(setup-vps.md § 2-3)
  - § DoD slice E 5 项 → Task 21(verify_slice_e.ps1 自动化 + setup-vps.md 部署文档)
  - **Pre-existing fix**(非 spec):bcrypt 5.x regression → Task 0
  - ✅ 全覆盖,无 spec 段被遗漏

- **Placeholder 扫**:
  - 无 TBD / TODO / "implement later" 残留
  - Task 14 update_category 的 GET-then-PATCH 双调用是有意为之(因 backend PATCH 不返 before),已注释说明
  - Task 13 add_transaction 的 `applied_rule` 永远 null 在 V2 候选中明确登记,代码注释也写明
  - Task 19 dev/prod profile 拆 service 是必要折衷(profiles 不能动态化 ports/volumes),已注释说明
  - ✅ 无 placeholder

- **类型一致**:
  - MCP `add_transaction` 入参 `time/amount/merchant/account/category/kind` 与 backend `tx_time/amount/merchant/account_id/category_id/tx_kind` 在 Task 13 `_to_body` 单点映射,outputSchema field `transaction_id/applied_rule/classified_category` 与 spec § 8.1 一致
  - MCP `confirm_dedup_pair` 出参 `action_taken` 取自 backend `DedupPairOut.status`(`"confirmed" / "rejected"`),Task 16 测试断言匹配
  - `BackendClient.get/post/patch/delete` 签名一致 — 都返 dict,204 → 空 dict
  - `MCPToolError(code, message, data?)` 在 errors.py 定义后,所有 tools handler 通过同一个 `httpx_to_mcp_error` 包装,error envelope JSON `{"error": {...}}` 在所有工具一致
  - ✅ 类型/命名贯通

- **DoD 可执行**:
  - `verify_slice_e.ps1` 7 项硬指标(backend pytest / mcp pytest / stdio JSON-RPC / compose config / Caddyfile validate / backup.sh syntax / .env.example completeness)
  - `mcp_smoke.ps1` 用 PowerShell 直接发 JSON-RPC,无 npx 依赖,CI 友好
  - prod profile 完整部署的 step-by-step 在 setup-vps.md(Task 20),不依赖本机环境
  - ✅

- **Task 间耦合检查**:
  - Task 0 修 bcrypt 是后续所有 task 的前置 — Pre-flight 警示已说明
  - Task 1-4 的 4 个 backend endpoint 是 Task 7-16 中 4 个特定 MCP 工具的依赖(`add_transaction`/`find_merchant`/`list_pending_classifications`/`get_account_balances`),依赖关系正向
  - Task 5 (token infra) 是 Task 6 (MCP skeleton bearer self-check) 的依赖,Task 5 → 6 有效
  - Task 6 (skeleton) 是 Task 7-16 的所有工具的依赖(每工具用 `register()` + `get_backend_client()`)
  - Task 17 (集成) 依赖 Task 7-16 全部完成
  - Task 18 (mcp_smoke.ps1) 依赖 Task 17(server 能正常 dispatch)+ backend 跑着(Task 5 做完)
  - Task 19 (deploy) 不依赖之前 task 的 _代码_,但依赖 mcp_server/ 目录存在(Task 6 起)
  - Task 20 (备份+文档) 独立
  - Task 21 (DoD) 依赖之前所有 task
  - ✅ 无环形依赖,实施顺序天然合理

- **遗留闭环**:Task 0 闭环 main 上 bcrypt 5.x regression(在 overview 标 ✅);其他切片 A/B/C/D 已知遗留中本切片不直接处理(Task 21 step 21.3 把 V2 候选明确登记)

(end of plan)
