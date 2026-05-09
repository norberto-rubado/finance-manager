# Finance Manager MVP 实施路线图(Overview Plan)

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each slice plan task-by-task.
>
> 本文档是**主路线图**,不含具体 step。每个切片有独立的详细 plan(`2026-05-08-mvp-slice-X-*.md`),实施时按切片进入对应详细 plan 执行。

**Goal:** 把已批准的 MVP spec(`2026-05-08-finance-manager-mvp.md`)落地为一个可在 VPS 上 24/7 运行的财务管家:浏览器电脑/手机端可用,OpenClaw/Hermes 通过 MCP 协议读写。

**Architecture:** 5 切片串行+部分并行交付。底层(数据库)→ 解析器 → 业务流水线 + API → UI + MCP + 部署。每切片独立产出可端到端验收的子集,验收通过再进下一切片。

**Tech Stack:** Python 3.11(Docker 容器内)/ FastAPI / SQLAlchemy 2 / Alembic / pdfplumber / openpyxl / rapidfuzz / Postgres 16 / Next.js 14 / shadcn/ui / Caddy / docker compose / Cloudflare DNS-01。

---

## 切片地图与依赖

```
切片 A:数据库基础(schema/Alembic/seed)        独立,起点
   │
   ├─▶ 切片 B:4 个账单解析器(纯函数,无 DB 写)   依赖 A 的 RawTransaction 数据结构
   │
   ▼
切片 C:导入流水线 + 去重 + 分类 + REST API      依赖 A + B
   │
   ├─▶ 切片 D:Web UI(Next.js 5 大板块)         依赖 C 的 REST API
   │
   └─▶ 切片 E:MCP server(10 工具)+ 部署(Caddy)  依赖 C(MCP 是 REST API 的薄包装)
```

**关键依赖说明:**
- 切片 B 不直接 import 切片 A 的代码 —— 它输出 `RawTransaction` dataclass,由切片 C 负责持久化。所以切片 B 在切片 A 写完 schema 后即可开始,**理论上 B 和 C 的部分前置任务可并行**(但单人开发建议串行,先 A → B → C)。
- 切片 D 和 E **可并行**(都依赖 C 的 REST API,互不依赖)。

---

## 各切片 DoD(Definition of Done)

每个切片完成的判定标准(端到端可验证):

### 切片 A:数据库基础
**DoD:** 在干净环境跑 `docker compose up db` + `alembic upgrade head` + seed 后,可以用 psql/DBeaver 连上,看到所有表创建完成、种子分类树和 25-30 条种子规则已经入库,关键表带正确索引。

**验收 SQL:**
```sql
SELECT count(*) FROM categories;        -- expect ≥ 12 (默认分类树)
SELECT count(*) FROM merchant_rules;    -- expect ≥ 25 (种子规则)
SELECT name FROM categories WHERE parent_id IS NULL ORDER BY sort_order;  -- 顶级分类
\d transactions                          -- 看字段+索引完整
```

### 切片 B:4 个解析器
**DoD:** 给定 4 份真实样本(支付宝 CSV / 微信 xlsx / 交行 PDF / 建行信用卡 PDF),每个解析器:
1. `detect()` 正确识别归属
2. `parse()` 输出的 `RawTransaction` 列表数量与样本头部"共 N 笔"一致(±5,允许过滤"交易关闭"等)
3. 抽样 3 笔交易字段值跟样本肉眼对比一致(金额/时间/商家)
4. 单元测试覆盖率 ≥ 80%(`pytest --cov=app.services.statement_parser`)
5. 信用卡解析器特别要验证:外币交易、银联还款入账、`财付通-X / 支付宝-X` 前缀识别

**验收命令:** `cd backend && pytest tests/services/statement_parser/ -v --cov`

### 切片 C:流水线 + API
**DoD:** 通过 HTTP 真实跑通完整路径:
1. `POST /api/auth/login` 用 admin 凭据拿 JWT
2. `POST /api/statements/import`(multipart upload)上传支付宝 CSV → 返回 import_id
3. `POST /api/statements/import` 上传交行 PDF → 后端**自动识别桥接重复**,返回 dedup_pending_count > 0
4. `GET /api/dedup/pending` 看到桥接对
5. `POST /api/dedup/{pair_id}/confirm` 确认或拒绝
6. `GET /api/transactions?limit=50` 看到所有交易,且已确认的 mirror 交易标 `is_mirror=true`
7. `GET /api/summary?period=month` 汇总数字与样本头部"支出 X 元"基本一致

**验收命令:** `bash tests/e2e/import_flow.sh`(切片 C 内会写一个端到端 shell 测试脚本)

### 切片 D:Web UI
**DoD:** 在浏览器(电脑 1920×1080 + 手机模拟 375×667)分别跑通:
1. 登录页输密码 → 跳首页 → 看到"本月概览"卡片
2. 进 `/statements` → 拖拽上传支付宝 CSV → 看到导入进度 → 自动跳 `/statements/{id}/review`
3. 复查页:左 tab 待审核去重对(逐对点确认/拒绝);右 tab 未分类(批量选 + 改类)
4. `/transactions` 列表能筛选/搜索/分页/批量改类
5. `/accounts` `/categories` `/rules` `/settings` CRUD 都能用
6. 切暗色模式;手机模拟下底部 tab bar 替代左侧导航
7. lighthouse 桌面/手机分数 > 80(performance + accessibility)

### 切片 E:MCP + 部署
**DoD:**
1. `python -m mcp_server.main` 启动后,用 MCP Inspector(`npx @modelcontextprotocol/inspector`)能列出 10 个工具
2. 每个工具用真实数据手测:read 工具返回结构化 JSON;write 工具能改 DB(然后 read 验证)
3. docker-compose 在干净 VPS 上 `docker compose up -d --profile prod` 一键起,Caddy 拿到证书,`https://your-domain:8443` 能用
4. `https://your-domain:9443/` 给 OpenClaw 配置后能列出工具+调用成功
5. 每天 03:00 cron 自动备份 + 加密 + 上传 R2 跑通(用 dry-run 模式测一次)

---

## 全局风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| **建行信用卡 PDF 表格抽取不稳** | 中 | 高(切片 B 卡住) | 切片 B 中此解析器**最后做**;先用 pdfplumber `extract_tables()`,失败用 `extract_text()` 行式正则备方案;真实样本只 3 页,出错可手工修复并退化成"半人工模式" |
| **支付宝 GBK 编码兼容性** | 低 | 中 | 用 `pandas.read_csv(encoding='gbk')`,异常时回退到 `gb18030` |
| **微信 xlsx 不同年份表头变化** | 中 | 中 | 解析器 detect() 通过表头第 18 行字符串严格匹配,变化时立即报错而不是吞 |
| **跨源去重误判(把不同支付的两笔错合)** | 中 | 高 | 强重复也建 `dedup_candidates` 留迹,confidence 字段记录算法路径,UI 暴露"可手工拆分镜像"的入口 |
| **MCP SDK 学习曲线** | 中 | 中 | 切片 E 第一个 task 是写 `hello_world` 工具跑通最小流程,再扩展到 10 工具 |
| **Caddy + caddy-dns/cloudflare 自定义镜像构建** | 低 | 中 | 优先用社区镜像 `slothcroissant/caddy-cloudflaredns`,备方案 `xcaddy build` |
| **VPS 防火墙配置错** | 低 | 高(被扫描攻击) | 切片 E 部署 task 包含 `ufw status verbose` 验证,只 22/8443/9443 |
| **数据库密码/MCP token 进 git** | 低 | 高 | 已经 .gitignore `.env`;切片 A task 1 会再确认一次;切片 E 部署前 git secret scan |
| **Windows 上 docker compose / Postgres 性能** | 低 | 低 | 开发用 WSL2 backend,如非必要不直接 Windows native |

---

## 环境准备(开发机:Windows 11)

**用户已有:** Python 3.14 / Git 2.52

**还需要安装(切片 A 第一个 task 会带):**
1. **Docker Desktop for Windows**(开 WSL2 backend)—— `winget install Docker.DockerDesktop`
2. **Python 3.11**(MVP 后端固定 3.11,跟 docker 镜像一致)—— `winget install Python.Python.3.11`
3. **Node.js 20 LTS**(切片 D 用)—— `winget install OpenJS.NodeJS.LTS`
4. **DBeaver Community**(可视化看 Postgres,可选)—— `winget install dbeaver.dbeaver`
5. **PowerShell 7.4+**(切片 E 部署脚本写 PS 兼容 bash 双版本)—— 已默认有

**为什么 Python 3.14 不直接用:** backend Dockerfile 固定 3.11(spec 已定),开发本机用 3.11 venv 跟容器一致,避免本地 pytest 的依赖装不下来或行为差异。3.14 留作其他项目用。

---

## 全局命名规约(贯穿所有切片)

- **Python 源码**:`snake_case` 函数/变量,`PascalCase` 类,`UPPER_SNAKE` 常量
- **数据库表/列**:`snake_case` 全小写,表名复数(`transactions`/`accounts`),外键 `*_id`
- **REST API 路径**:`/api/<resource>` 复数(`/api/transactions`),动作 `/api/dedup/{id}/confirm`
- **MCP 工具名**:`snake_case` 动词开头(`list_transactions` / `add_transaction`)
- **Next.js 路由**:`/transactions` 复数,动态段 `[id]`(`/statements/[id]/review`)
- **TS 类型/组件**:`PascalCase`(`TransactionList`),hooks `useXxx`
- **commit message 前缀**:`feat / fix / refactor / docs / test / chore / ci`
- **commit 体**:中英文都行,但代码相关术语一律英文
- **每个 step 完成立即 commit**,不批量

---

## 阅读顺序

实施时按编号进入对应切片 plan:

1. 现在:阅读本 overview,理解切片地图和 DoD
2. **进入 [`2026-05-08-mvp-slice-a-database.md`](./2026-05-08-mvp-slice-a-database.md)** —— 切片 A 详细 plan
3. 完成切片 A 并验收通过后,回到这里(我会基于 A 的实际产出写切片 B 详细 plan)
4. 后续切片同理

每完成一个切片,**回到这里更新 § 完成进度**(下方表格)。

---

## 已知遗留问题(切片 A → 后续切片处理)

切片 A final review(Senior Code Reviewer)在 `slice-a-database` 分支末尾提出,**所有问题均不阻塞 slice A merge**(I-2 已在 commit 9a43dd6 修复),其余条目交给后续切片处理:

### 切片 B 启动前必修(已闭环)

- ~~**I-1** `transactions(user_id, tx_time DESC)` 索引缺少 DESC~~ ✅ 已在 slice B Task 1 修复(commit `0e349f0`)
- ~~**I-3** 测试速度过慢(8 tests 跑 4m21s,truncate 策略瓶颈)~~ ✅ 已在 slice B Task 2 改为 nested-savepoint(commit `5cb2353` + `8a55895`),全测试套件从 4m21s → 24s

### 切片 C 启动前必修

- **I-5** `seed.ensure_default_user` 中 `password_hash="$2b$12$placeholder_replace_in_slice_c"` 不是合法 bcrypt hash。slice C 实现 `/api/auth/login` 时,需要从 Settings 读 `admin_password_hash` 替换占位符。
- **Recommendation #5**:`merchant_rules` 中 priority=20 的 6 条"跨源标记"规则 `category_id=NULL`。slice C 规则分类引擎要正确处理 `category_id IS NULL`(跳过分类、仅做标记),不能简单 `if category_id: assign`。建议在 `MerchantRule` 上加 `is_marker: bool` 或通过 `priority<30` 的约定区分。
- **Recommendation #3-4**:`source_unique_key` 是 `nullable=True + unique=True`,Postgres 中允许多个 NULL 共存(对 conversation/manual 来源是正确行为)。slice B 解析器接口需固定生成格式 `f"{source}:{external_tx_id}"`,确保 bank/alipay/wechat 来源必填。

### Polish(slice B 产生,后续可清理)

- **B-poly-1** `ccb_credit_pdf.py` 用 codepoint set 匹配中文(`_has_codepoints` / `_identify_currency`),实质是把 Windows GBK 终端显示乱码误判为 PDF 字体编码问题。pdfplumber 实际抽取的是标准 UTF-8。建议改回标准字符串子串匹配(`"银联" in s and "入账" in s`),并修正 docstring 中"自定义字体 subset"的误导说明。
- **B-poly-2** `_is_repayment("联银账入")` 等乱序输入会误返回 True(因为用 set comparison)。改为子串顺序匹配可消除。
- **B-poly-3** `wechat_xlsx.py` 的 `_to_str` 把 "/" 字面值视为占位符,会误处理真实商户名含 "/" 的情况(如 "A/B 公司")。本切片真实样本未触发,留待 slice C 分类引擎遇到时处理。
- **B-poly-4** `seed.py` 真实 `python -m app.db.seed` 跑后会在 dev db 留持久 admin 行,导致 test 必须用 `ON CONFLICT` 兜底(已在 commit `80e6908` 解决)。根本修复:slice C 启动 finance_test 独立 db 后启用 TEST_DATABASE_URL。

### Polish(后续任意切片处理)

- **I-4** `seed_default_categories` 返回值"总数"(46)而非"新增数",二次跑误导运维。改为返回 `(created, total)` 或仅 `created`。
- **M-1** `alembic.ini` 的 `post_write_hooks` 配置 ruff,但 venv 外执行时找不到。改用 `python -m ruff` 或显式 venv 路径。
- **M-2** `conftest.py` 的 `db` fixture rollback 注释有误导,应说明数据靠 `_truncate_between_tests` 清理。
- **M-3** `test_seed_*` 断言用 `>= 12 / >= 25` 太松,应改为 `== 46 / == 29` 严格匹配。
- **M-4** `config.py` 的 `Union[str, List[str]]` 改 PEP 604 风格 `str | list[str]`。
- **M-5** `TimestampMixin.updated_at` 的 `onupdate=func.now()` 仅 ORM 层生效,裸 SQL 不更新。base.py docstring 说明限制。
- **M-6** `.env.example` 中 `DATABASE_URL=...@db:5432` 是 docker 内网 host,本机 venv 应用 `localhost`。加注释说明两种用法。

---

## 完成进度

| 切片 | 状态 | 完成日期 | 实际工时 | 备注 |
|---|---|---|---|---|
| A. 数据库基础 | ✅ 完成 | 2026-05-08 | (实施工时由 controller 估算) | DoD verify script passed; final review approved with I-2 fix in 9a43dd6 |
| B. 4 个解析器 | ✅ 完成 | 2026-05-09 | (实施工时由 controller 估算) | DoD verify script passed; 4 parsers cov ≥ 80%; 137 tests pass; I-1/I-3 also resolved; 真实 4 份样本入仓 |
| C. 流水线 + API | 未开始 | — | — | — |
| D. Web UI | 未开始 | — | — | — |
| E. MCP + 部署 | 未开始 | — | — | — |

(end of overview)
