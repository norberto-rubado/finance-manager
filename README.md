# Finance Manager — 个人财务管家 MVP

一个可 24/7 部署在 VPS 上的个人财务后端与 Web UI：

- 浏览器访问 Web UI（Next.js + shadcn/ui）
- 上层 Agent（OpenClaw / Hermes Agent 等）通过 MCP 协议读写数据
- 后端零 LLM 依赖：所有 AI 推理都在 Agent 侧完成
- 支持账单导入、去重、分类、统计、REST API、MCP 工具与 Docker/Caddy 部署

## 当前状态

MVP 已完成 5 个切片：

- ✅ A. 数据库基础
- ✅ B. 4 个账单解析器
- ✅ C. 导入流水线 + 去重 + 分类 + REST API
- ✅ D. Web UI
- ✅ E. MCP server（10 工具）+ 部署脚本

最近部署前修复：

- 修复 FastAPI `get_db()` 请求成功后未提交事务的问题
- 为真实 `get_db` 生命周期添加回归测试
- 修复 `.env.example` 中 bcrypt hash 被 docker-compose `$` 插值的问题

## 技术栈

| 模块 | 技术 |
|---|---|
| Backend | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL |
| Parser | pandas, openpyxl, pdfplumber |
| Frontend | Next.js 14 App Router, TypeScript, shadcn/ui, Tailwind CSS |
| MCP Server | Python MCP SDK, httpx |
| Deploy | docker-compose, Caddy, Cloudflare DNS-01, Postgres 16 |
| Test | pytest, Vitest, Playwright |

## 仓库结构

```text
finance-manager/
├── backend/                 # FastAPI backend + Alembic + pytest
├── frontend/                # Next.js Web UI
├── mcp_server/              # MCP server，暴露 10 个工具
├── docs/superpowers/        # spec、plans、切片记录
├── scripts/                 # VPS 部署与备份脚本
├── docker-compose.yml       # dev/prod profiles
├── Caddyfile                # HTTPS reverse proxy
├── .env.example             # 环境变量模板
└── CLAUDE.md                # 项目上下文与开发约定
```

## 本地开发

### 1. 克隆项目

```bash
git clone https://github.com/norberto-rubado/finance-manager.git
cd finance-manager
```

### 2. 准备环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD_HASH`

注意：bcrypt hash 必须保留单引号，避免 docker-compose 插值：

```env
ADMIN_PASSWORD_HASH='$2b$12$...'
```

### 3. 启动 Postgres

本项目按现有开发约定使用横线版命令：

```bash
docker-compose --profile dev up -d db
```

### 4. Backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.db.seed
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 5. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

访问：<http://localhost:3000>

### 6. MCP Server

```powershell
cd mcp_server
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:MCP_BACKEND_URL="http://127.0.0.1:8000"
$env:MCP_API_TOKEN="<从后台生成的 token>"
.\.venv\Scripts\python.exe -m app.main --transport http --host 0.0.0.0 --port 8765
```

## VPS 生产部署

详细步骤见：[`scripts/setup-vps.md`](scripts/setup-vps.md)

简版流程：

```bash
cd /opt
git clone https://github.com/norberto-rubado/finance-manager.git
cd finance-manager
cp .env.example .env
nano .env

docker-compose --profile prod up -d --build
docker-compose --profile prod ps
```

生产入口：

- Web UI + REST API：`https://<DOMAIN>:8443`
- MCP HTTP endpoint：`https://<DOMAIN>:9443`

## 常用验证命令

Backend：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check app
```

Frontend：

```bash
cd frontend
pnpm typecheck
pnpm lint
pnpm test:unit
```

MCP Server：

```powershell
cd mcp_server
..\backend\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest tests -q
```

Slice E 综合验证：

```powershell
pwsh backend\scripts\verify_slice_e.ps1
```

## 核心文档

建议按顺序阅读：

1. [`docs/superpowers/specs/2026-05-08-finance-manager-mvp.md`](docs/superpowers/specs/2026-05-08-finance-manager-mvp.md)
2. [`docs/superpowers/plans/2026-05-08-mvp-overview.md`](docs/superpowers/plans/2026-05-08-mvp-overview.md)
3. [`scripts/setup-vps.md`](scripts/setup-vps.md)

## 安全提示

- 不要提交 `.env`、真实账单、API token、私钥或数据库备份
- 生产环境 `.env` 建议 `chmod 0600`
- `ADMIN_PASSWORD_HASH` 使用 bcrypt hash，不要写明文密码
- MCP token 只在创建时显示一次，部署后写入 `.env`
- 备份脚本使用 age 加密后上传 R2，详见 `scripts/backup.sh`

## License

未指定许可证。私有/个人项目使用前请先确认授权范围。
