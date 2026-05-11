# Dashboard + Budget 实施路线图(Overview Plan)

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each slice plan task-by-task.
>
> 本文档是**主路线图**,不含具体 step。每个切片有独立的详细 plan(`2026-05-11-dashboard-slice-X-*.md`),实施时按切片进入对应详细 plan 执行。

**Goal:** 落地 spec(`2026-05-11-dashboard-budget-design.md`)—— 新建 `/dashboard` 路由,提供"日常追踪 + 预算监控"主场景 + "月底复盘"次场景;后端补 `budgets` 模型 + 5 个端点;首页 `/` 保持原状,仅加跳转入口。

**Architecture:** 5 切片串行交付。后端基础(预算 CRUD)→ 后端汇总(snapshot)→ 前端骨架(上半区)→ 前端深化(类别列表 + 设置页)→ 前端复盘 + e2e + polish。每切片独立产出可端到端验收的子集。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2 / Alembic / Postgres 16 / Next.js 14 App Router / TypeScript / shadcn/ui / Tailwind / Recharts 2.13 / Playwright / Vitest / pytest。

---

## 切片地图与依赖

```
切片 A:budgets 表 + CRUD API           独立,起点
   │
   ▼
切片 B:/dashboard/snapshot API         依赖 A(查 budgets 表)
   │
   ▼
切片 C:前端 /dashboard 骨架 + 上半区    依赖 B(消费 snapshot)
   │
   ▼
切片 D:类别列表 + 内联编辑 + 待办      依赖 A(PUT /budgets)+ C(骨架)
   │
   ▼
切片 E:复盘区 + 设置页 + 移动端 + e2e   依赖 A + B + C + D 全部
```

**关键依赖说明:**
- 切片 A 和 B 都是纯后端,无需前端可独立验证(curl + pytest)
- 切片 C 启动后,前端可看到上半区(预算环 / 节奏卡 / 累计图),即使下半区组件还没写
- 切片 D 完成后,功能闭环:从 dashboard 改预算 → 立刻反映;切片 E 是"复盘区 + 配置页 + 测试 + 移动端 polish",可砍可保(若工期紧)

---

## 各切片 DoD(Definition of Done)

### 切片 A:budgets 表 + CRUD API

**DoD:**
1. Alembic 迁移在干净 db 跑过,`budgets` 表 + 两个 partial unique index 都存在
2. 5 个 API 端点(`GET / PUT / DELETE /budgets`、`POST /budgets/copy-from`)都通过认证 + 业务测试
3. 唯一约束:同月同 category(非 NULL)只能一条;同月总预算(category_id IS NULL)只能一条
4. copy-from 边界:上月有数据 / 上月无数据 / 目标月已有数据(返 409)三种情况都正确

**验收命令:**
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/api/test_budgets.py tests/models/test_budget.py -v
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade -1   # 验证 downgrade 不报错
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 切片 B:dashboard snapshot API

**DoD:**
1. `GET /api/dashboard/snapshot?year=&month=&client_date=` 在 5 个场景下返回正确 JSON:
   - 无任何预算(total.budget = null,categories[].budget 全 null,three_month_avg 有值)
   - 月初 1 号(pace.expected_ratio = 1/total_days)
   - 上月无数据(total.prev_month_spent = "0")
   - 类别已超(pending.overspending_count > 0,对应 category is_overspending = true)
   - 非本月查询(period.is_current_month = false,pace.expected_ratio = 1.0,pending 全 0)
2. P95 响应 < 300ms(在 1000 条 transaction 的样本数据下)

**验收命令:**
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/api/test_dashboard.py tests/services/test_dashboard.py -v
# 手动验证
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# 另一个终端:
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"...\"}" -c cookie.txt
curl "http://localhost:8000/api/dashboard/snapshot?year=2026&month=5&client_date=2026-05-11" -b cookie.txt | jq .
```

### 切片 C:前端 /dashboard 骨架 + 上半区

**DoD:**
1. 浏览器访问 `http://localhost:3000/dashboard` → 看到:
   - 顶部 MonthPicker(默认本月)
   - 大型预算环(若未设预算显示"未设总预算 [立即设置 →]")
   - 月节奏卡(显示"第 X/Y 天 / 应用 N% / 实用 M%")
   - 累计支出曲线 vs 预算斜线
2. 切换 MonthPicker 到上月 → URL 同步 + 数据刷新 + 月节奏卡消失
3. 网络断 → 看到 EmptyState 红字 + Retry 按钮
4. 手机模拟 375px 单列布局不溢出
5. 首页 `/` KPI 卡片右上加 "详查 →" 链接到 `/dashboard`

**验收命令:**
```bash
cd frontend
pnpm dev
# 浏览器手动验证上述 5 条
pnpm typecheck
pnpm lint
pnpm test:unit -- dashboard
```

### 切片 D:类别列表 + 内联编辑 + 待办

**DoD:**
1. `/dashboard` 类别列表显示所有 expense 类别;有预算的进度条带颜色;无预算的虚线 + 显示"vs 均 ¥X"
2. 点击类别行 `[⚙]` → popover 出现 amount + note → 保存 → 进度条立即更新
3. 点击"待办 chip"跳到对应页(超支锚定列表 / 未分类 → /transactions?category_id=null / 待审核 → /statements)
4. `/settings/budgets` 页面可设置总预算 + 各类别预算 + note,可"复制上月"
5. RTL 单测覆盖:`<CategoryBudgetList>` 的 budget=null / 有 budget 两态、内联保存 happy

**验收命令:**
```bash
cd frontend
pnpm dev
# 浏览器:点 ⚙ 改预算 → 数字变 → 刷新仍保留
# 浏览器:进 /settings/budgets → 设置 → 返回 /dashboard 看到变化
pnpm test:unit -- category-budget-list budget-row-editor
```

### 切片 E:复盘区 + 移动端 polish + e2e

**DoD:**
1. `<CategoryDonut>`:本月分类占比,Top 5 + 其他,中心显示总额
2. `<MonthlyTrendBars>`:过去 6 个月支出柱状,当月柱用 primary 高亮
3. 移动端 375px:类别列表只显示 Top 5 + "展开全部";累计图高度 200px;⚙ 按钮改为整行点击
4. Playwright 跑通 2 条 e2e:
   - **path 1 (happy)**:登录 → /dashboard → 内联改一个类别预算 → 数字立刻变 → 刷新 → 值仍保留
   - **path 2 (时间窗)**:进 /dashboard → 切到上月 → 月节奏卡消失 + 累计图变整月 + 待办卡消失
5. 整页视觉对一次(暗色模式 + 浅色模式各一遍)

**验收命令:**
```bash
cd frontend
pnpm test:e2e -- dashboard
pnpm typecheck
pnpm lint
pnpm build   # 构建无 warning
```

---

## 全局风险 / 路径切换

| 风险 | 缓解 |
|---|---|
| 切片 B 的 `compute_dashboard_snapshot()` 跑得慢(N+1 嫌疑) | 切片 B 内部跑 pytest 时打印耗时;若 > 200ms 当场改成 1 条 `GROUP BY (year, month)` SQL |
| 前端 Recharts 在 dark mode 颜色不显眼 | 切片 C 实施时,先做一个 minimal chart 验证 `hsl(var(--primary))` 的渲染效果,不行就退回硬编码 emerald-500 |
| 内联编辑乐观更新导致脏数据 | 失败 toast 后 revert 输入框;同时调一次 `getSnapshot()` 强同步 |
| 切片 E 工期紧 | 砍掉 `<CategoryDonut>` 或 `<MonthlyTrendBars>`(复盘场景的"锦上添花"),保留 e2e 不砍 |

---

## 实施顺序建议

**单人开发**:严格 A → B → C → D → E,每切片完成跑完 DoD 验收命令再进下一个。

**两人开发**:
- 后端工程师跑 A → B,完成后可并行做 backend 性能 polish 或转去帮前端
- 前端工程师在 A 完成后就可以开始 C(用 mock snapshot 数据),B 完成后切真实 API

---

## 完成 DoD(整体)

5 个切片全部 DoD 通过 + 下面三条端到端 smoke test:

1. **新用户路径**:全新账号 → 进 /dashboard 显示"未设总预算" → 进 /settings/budgets 填总额 + 几个类别 → 回 /dashboard 看到预算环 + 类别条
2. **日常监控路径**:进 /dashboard → 看到"本月已花 ¥X / ¥Y, 提前 N%"判断 → 点超支 chip 跳到那个类别
3. **复盘路径**:MonthPicker 切到上月 → PaceCard 消失 → CategoryDonut 显示上月分类占比 → 6 月趋势柱状中上月柱高亮显示

整体工作量预估 **9 个工作日**(单人节奏)。
