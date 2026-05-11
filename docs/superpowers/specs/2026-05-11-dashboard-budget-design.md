# Dashboard + Budget — 设计文档

| 字段 | 内容 |
|---|---|
| 状态 | Draft(brainstorming → spec) |
| 日期 | 2026-05-11 |
| 范围 | 新建 `/dashboard` 路由 + 后端 `budgets` 模型 / API,覆盖"日常追踪 + 预算监控"主场景与"月底复盘"次场景 |
| 不动 | 首页 `/`(只加一个跳转入口) |
| 依赖 | 现有 `/summary` API、`categories` 树形表、`transactions` 表;Recharts、shadcn/ui、sonner |
| 前置约定 | dark mode default、Inter + Noto Sans SC、CSS variable 配色 |

---

## 1. 背景与目标

### 1.1 现状
现有首页 `/` 提供本月概览:4 张 KPI 卡(支出 / 收入 / 净额 / 待审核)、近 7 天支出折线图、最近 10 笔交易。功能上"看一眼今天/本月的样子"够用,但:
- KPI 卡密度低,无趋势 / 环比 / 占比信息
- 只有单条折线图,缺少分类占比、累计 vs 预算、月度趋势等维度
- 没有"该处理什么"的行动召唤(待审核数字不可点)
- 没有预算约束,看完不知道"还能花多少"

### 1.2 目标
新建 `/dashboard` 页,主要回答两个问题:
1. **(主)今天我还能花多少?会不会超?** —— 日常追踪 + 预算监控
2. **(次)上个月花在哪了?** —— 月底复盘

首页 `/` 保持轻量速览定位,只在右上角加入口跳到 `/dashboard`。

### 1.3 非目标(out of scope)
- 年预算、周预算(只做月预算)
- 多账户余额预测、储蓄目标进度
- 推送 / 邮件超支提醒(仅 UI 内告警)
- 父子分类自动汇总(父类不能单独设预算;若用户在父类设了,等同于其他叶子的兄弟节点)
- 预算结转(carry over):本月没花完不滚到下月

---

## 2. 范围与边界

### 2.1 In-scope

| 模块 | 内容 |
|---|---|
| 后端数据模型 | `budgets` 表:月度,可选 `category_id`(null 表总预算),可选 `note` |
| 后端 API | 5 个端点:CRUD + copy-from + dashboard snapshot |
| 前端路由 | `/dashboard`、`/settings/budgets`(若 settings 已有内容,合入为 tab) |
| 前端组件 | 8 个 dashboard 组件 + 2 个 budget 设置组件 |
| 时间窗 | 顶部 month picker;支持任意月份;URL 持久化 |
| 测试 | 后端 unit + integration;前端 unit + RTL + 2 条 e2e |

### 2.2 Out-of-scope(V2)
- 年预算 / 周预算
- 预算结转
- 类别父子预算自动聚合
- 主动推送 / 邮件超支告警
- 预测月末花费

---

## 3. 整体架构

### 3.1 数据流

```
┌──────────────────────────────────────────────────────────────┐
│  Browser                                                      │
│  /dashboard ──┬─→ GET /dashboard/snapshot?year=&month=        │
│               │                                                │
│  内联调整 ────┴─→ PUT /budgets (category_id, amount, note)    │
│               └─→ optimistic update → 后台再 GET snapshot 一次 │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI                                                      │
│  /budgets        CRUD + copy-from                             │
│  /dashboard/snapshot  ←─ 一次 query 返回 7 块数据             │
│                                                               │
│  依赖:budgets 表、categories 树、transactions 表             │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 预算实现 | 后端完整表 + API(非 localStorage) | 多设备同步、可备份、统一数据源 |
| 预算颗粒度 | 月总预算 + 类别预算,二者独立 | 既能"控总额"又能"控分项",类别可只设部分 |
| 预算未设兜底 | 显示过去 3 个月该类别均值 | dashboard 不留空白,引导用户参考 |
| 周期 | 仅月预算(每月 1 号重置) | MVP 简化;后续扩 `period` 字段即可 |
| 数据接口 | `/dashboard/snapshot` 打包式 | 减少瀑布请求、保证快照一致性 |
| 时间窗 | URL `?year=&month=` | 可分享、可刷新、可前进/后退 |
| 设置入口 | `/settings/budgets` 主入口 + dashboard 内联快调 | 主入口完整管理,快调日常微调 |

---

## 4. 后端设计

### 4.1 `budgets` 表

```python
class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)   # 2026
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..12
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )  # NULL = 该月总预算
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        Index("ix_budgets_user_period", "user_id", "period_year", "period_month"),
        # 唯一约束:NULL 也算唯一(Postgres 默认 NULL 不等,所以拆两个 partial unique index)
        # 见 migration
    )
```

### 4.2 Migration 关键点

Postgres `UNIQUE (user_id, period_year, period_month, category_id)` 在 `category_id IS NULL` 时**不会约束唯一**(NULL 互不相等)。需用**两个 partial unique index**:

```sql
-- 同月同 category(非 NULL)只能一条
CREATE UNIQUE INDEX uq_budget_period_category
  ON budgets (user_id, period_year, period_month, category_id)
  WHERE category_id IS NOT NULL;

-- 同月总预算(category_id IS NULL)只能一条
CREATE UNIQUE INDEX uq_budget_period_total
  ON budgets (user_id, period_year, period_month)
  WHERE category_id IS NULL;
```

### 4.3 Schemas

```python
class BudgetIn(BaseModel):
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    category_id: int | None = None   # None = 总预算
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)

class BudgetOut(BudgetIn):
    id: int
    created_at: datetime
    updated_at: datetime
```

### 4.4 API 端点

| Method | Path | Body / Query | 返回 | 用途 |
|---|---|---|---|---|
| `GET` | `/budgets` | `?year=2026&month=5` | `list[BudgetOut]` | 设置页列出本月所有预算 |
| `PUT` | `/budgets` | `BudgetIn` | `BudgetOut` | upsert(按 (user, year, month, category) 主键) |
| `DELETE` | `/budgets/{id}` | — | `204` | 删一条 |
| `POST` | `/budgets/copy-from` | `{from_year, from_month, to_year, to_month}` | `list[BudgetOut]` | 复制上月所有预算到本月;若目标月已有 → 409 |
| `GET` | `/dashboard/snapshot` | `?year=2026&month=5&client_date=2026-05-11` | `DashboardSnapshot` | dashboard 主接口;`client_date` 是前端本地时区的"今天",后端用它算 `is_current_month` / `day_of_month`,避免 UTC 跨月偏移 |

### 4.5 `/dashboard/snapshot` 响应契约

```ts
type DashboardSnapshot = {
  period: {
    year: number;
    month: number;
    day_of_month: number;        // 1..31,非本月查询时 = total_days
    total_days: number;           // 该月总天数
    is_current_month: boolean;    // 前端用以隐藏 PaceCard / PendingActions
  };
  total: {
    budget: string | null;        // null = 未设总预算
    spent: string;
    income: string;
    prev_month_spent: string;
  };
  pace: {
    expected_ratio: number;       // day_of_month / total_days
    actual_ratio: number | null;  // spent / budget;无总预算 = null
    delta_pct: number | null;     // (actual - expected) / expected * 100
  };
  categories: Array<{
    category_id: number;
    name: string;
    icon: string | null;
    color: string | null;
    budget: string | null;        // null = 未设
    spent: string;
    three_month_avg: string;      // 过去 3 个完整月均值(不含本月)
    note: string | null;
    is_overspending: boolean;     // spent > budget(仅当 budget 非 null)
  }>;
  monthly_trend: Array<{          // 含查询月在内,向前 6 个月,升序
    year: number;
    month: number;
    expense: string;
    income: string;
  }>;
  pending: {                       // 非本月 → 全 0(前端隐藏)
    uncategorized_count: number;
    dedup_pending_count: number;
    overspending_count: number;   // categories 里 is_overspending 之和
  };
};
```

### 4.6 关键算法

**三月均值**:
- 取查询月前 3 个完整月(不含查询月本身)
- 每月按 category_id 聚合 `tx_kind='expense'` 的 `amount` 之和
- 三月之和 / 3 → 该类别 `three_month_avg`
- 不足 3 个月数据 → 用实际有数据的月数分母(N >= 1);N = 0 → `three_month_avg = "0"`

**节奏 expected_ratio**:
- 后端用 `client_date` 与 query `year/month` 比较:相同 → `is_current_month = True`,`day_of_month = client_date.day`;否则 `is_current_month = False`,`day_of_month = total_days`(整月已过)
- 本月:`expected_ratio = day_of_month / total_days`
- 非本月:`expected_ratio = 1.0`

**delta_pct**:
- `actual_ratio - expected_ratio` 再除以 `expected_ratio` 再 × 100
- 正值 = 花得快(提前超线),负值 = 花得慢
- `budget = null` 或 `expected_ratio = 0` → `delta_pct = null`

**overspending**:
- 仅在 `budget is not None` 时判定
- `spent > budget` 即 true

### 4.7 后端服务层

```
backend/app/services/
├── budget.py            # 新:CRUD helpers + copy-from
└── dashboard.py         # 新:compute_dashboard_snapshot()
                         #     复用 services/summary.compute_summary()
                         #     额外查 budgets + 三月均值
```

`compute_dashboard_snapshot()` 内部调用次数预估:
- 1 次查 `budgets`(本月所有行)
- 1 次 `compute_summary` 拿本月分类支出
- 1 次 `compute_summary` 拿上月支出(只要 total)
- 3 次 `compute_summary` 拿前 3 个月各月分类支出(算均值)
- 6 次 `compute_summary` 拿过去 6 个月 total(给 trend bars)
- 2 次 count(未分类 / dedup_pending)

共 ~13 次查询。如压力大,后续改成 1 条 `GROUP BY (year, month, category_id)` 的 SQL。MVP 先保持可读性。

---

## 5. 前端设计

### 5.1 路由

| 路径 | 文件 | 功能 |
|---|---|---|
| `/dashboard` | `app/(app)/dashboard/page.tsx` | 主页 |
| `/settings/budgets` | `app/(app)/settings/budgets/page.tsx` 或 settings 内 tab | 预算管理 |

`/` 首页 KPI 卡片右上角加 `[详查 →]` 链接到 `/dashboard`(单行改动)。

### 5.2 文件结构

```
frontend/
├── app/(app)/
│   ├── dashboard/page.tsx                # 新
│   └── settings/budgets/page.tsx         # 新(或合入 settings 已有页)
├── components/
│   ├── dashboard/                        # 新
│   │   ├── month-picker.tsx
│   │   ├── budget-summary-card.tsx
│   │   ├── month-pace-card.tsx
│   │   ├── cumulative-chart.tsx
│   │   ├── category-budget-list.tsx
│   │   ├── pending-actions-card.tsx
│   │   ├── category-donut.tsx
│   │   └── monthly-trend-bars.tsx
│   └── budgets/                          # 新
│       ├── budget-row-editor.tsx         # 设置页表格行
│       └── copy-from-prev-button.tsx
└── lib/api/
    ├── budgets.ts                        # 新:CRUD + copy-from
    └── dashboard.ts                      # 新:getSnapshot
```

### 5.3 组件职责

| 组件 | 数据 | 形态 | 非本月行为 |
|---|---|---|---|
| `<MonthPicker>` | URL state | shadcn dropdown,显示"本月"/"上月"/"YYYY 年 M 月" | 自身就是控制器 |
| `<BudgetSummaryCard>` | `total.budget/spent`、`pace.actual_ratio` | 大型 SVG 环 + 中心金额 + 剩余 + "管理预算"链接 | 环仍画,label 改"该月已用/预算" |
| `<MonthPaceCard>` | `pace`、`total.prev_month_spent` | 4 块小数字:第 X/Y 天 / 应用 % / 实用 % / vs 上月 ↑↓ | **整卡 hidden** |
| `<CumulativeChart>` | 当月日累计 + 预算斜线 | Recharts `ComposedChart`:`Area`(实际)+ `Line`(预算斜线) | 本月画到今天;非本月画整月 |
| `<CategoryBudgetList>` | `categories[]` | 每行:icon + 名 + 进度条 + 金额 / 预算 + 内联编辑 ⚙ | ⚙ 按钮 hidden |
| `<PendingActionsCard>` | `pending` | 3 个 chip 链接:超支 N 类(锚到列表)/ 未分类 N 笔(→ /transactions)/ 待审核 N 对(→ /statements) | **整卡 hidden** |
| `<CategoryDonut>` | `categories[].spent` Top 5 + 其他 | Recharts `PieChart`(donut hole),中心总额 | 跟随时间窗 |
| `<MonthlyTrendBars>` | `monthly_trend[]` | Recharts `BarChart` 6 柱,当月柱用 primary,其他用 muted | 跟随时间窗滑动 |

### 5.4 时间窗

URL contract:
- `/dashboard` (无 query) → 前端**用本地时区** `new Date()` 计算 year/month,立即 `router.replace` 写入 URL
- `/dashboard?year=2026&month=4` → 指定月

实现:
- 用 `useSearchParams()`(同 `transactions/page.tsx` 风格),包 `<Suspense>` 防 SSG bailout
- `<MonthPicker>` 选择后 `router.push` 更新 URL
- 后端 `/dashboard/snapshot` 强制要求 `year + month` query,不做"无参数默认本月"逻辑 —— 这样"本月"的定义由前端本地时区决定,跨月边界更符合用户感知(中国用户 23:00 仍是当月,北京 0:01 切到新月,不会因为 UTC 滞后 8 小时显示上月)

### 5.5 类别列表内联编辑

```
餐饮     ████████░░  ¥1450 / ¥1500  [⚙]
交通     ███░░░░░░░  ¥320  / ¥1000  [⚙]
娱乐     ─────────── ¥180  vs 均 ¥250 ↓  [⚙]   ← 未设预算
```

- 进度条颜色:`< 80% emerald` / `80–100% amber` / `> 100% rose`
- `[⚙]` 点击 → shadcn `Popover` 出现 amount input + note input + 保存按钮
- 保存:`PUT /budgets` → 成功后乐观更新列表 + 后台再 `GET /dashboard/snapshot`
- 未设预算行:进度条变虚线,后缀显示 `vs 均 ¥X ↑/↓`

### 5.6 加载策略

- 进入 `/dashboard`:`useEffect` 触发 `getSnapshot()`
- 加载中:整页骨架(8 个 `<Skeleton>`)
- 错误:`<EmptyState>` 红字 + Retry 按钮
- 内联编辑后:不 block UI,toast 提示成功 / 失败

---

## 6. UI / UX

### 6.1 桌面布局(≥ 1024px)

```
┌─────────────────────────────────────────────────┐
│ Dashboard                          [本月 ▾]      │
├─────────────────────────────────────────────────┤
│ ┌────────────────┬────────────────────────────┐ │
│ │ <BudgetSummary>│ <MonthPace>                │ │
│ └────────────────┴────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ <CumulativeChart>(全宽)                     │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────┬───────────────────────┐ │
│ │ <CategoryBudgetList>│ <PendingActions>      │ │
│ └─────────────────────┴───────────────────────┘ │
│ ┌─────────────────┬─────────────────┐           │
│ │ <CategoryDonut> │ <MonthlyTrend>  │           │
│ └─────────────────┴─────────────────┘           │
└─────────────────────────────────────────────────┘
```

### 6.2 平板(768–1023px)

- 同桌面布局,`<CumulativeChart>` 高度从 320px 降到 240px

### 6.3 手机(< 768px)

- 全部纵向单列
- `<CategoryBudgetList>` 默认只显示 Top 5,底部 "展开全部"
- 进度条占满行宽,`[⚙]` 改为整行可点(增大命中区,符合 44pt touch target)
- `<CumulativeChart>` 高度 200px

### 6.4 配色 / 视觉

- 进度条阈值:`< 80%` emerald-500,`80–100%` amber-500,`> 100%` rose-500
- 全部走 shadcn CSS variable(`hsl(var(--primary))`、`hsl(var(--muted))` 等)
- 图表 grid line 用 `--border`,axis label 用 `--muted-foreground`
- 暗色模式默认(项目已配)

### 6.5 Empty / Loading / Error

| 场景 | 处理 |
|---|---|
| Snapshot loading | 8 个 `<Skeleton>` + 标题占位 |
| Snapshot error | `<EmptyState>` + Retry |
| 内联保存失败 | `toast.error()` + 输入框 revert |
| 全新用户(无任何交易) | 预算环显示 ¥0,类别列表 "还没导入账单 [去导入 →]" |
| 从未设过任何预算 | 预算环中央 "未设总预算 [立即设置 →]" |
| 类别预算之和 > 总预算 | settings 页头部红条警告;dashboard 不报错 |

---

## 7. 测试策略

### 7.1 后端

| 文件 | 覆盖 |
|---|---|
| `tests/models/test_budget.py` | 唯一约束(NULL + 非 NULL 两种 partial index) |
| `tests/api/test_budgets.py` | CRUD happy / 422 / 越权;copy-from(上月有 / 上月无 / 目标月已有) |
| `tests/api/test_dashboard.py` | snapshot 在 5 场景:无预算 / 月初 1 号 / 上月无数据 / 类别已超 / 非本月 |
| `tests/services/test_dashboard.py` | 三月均值算法(N=0/1/2/3)、节奏算法、overspending 判定 |

### 7.2 前端

| 类型 | 覆盖 |
|---|---|
| vitest unit | 进度条颜色阈值函数、pace 文案、月份选择器格式化 |
| vitest + RTL | `<BudgetSummaryCard>` budget=null / 有 budget 两态;`<CategoryBudgetList>` 内联编辑 happy |
| Playwright e2e (2 条) | (1) 主流程:登录 → /dashboard → 内联改预算 → 数字变 → 刷新仍保留;(2) 时间窗切换:切到上月 → PaceCard / PendingActions 消失,Cumulative 变整月 |

---

## 8. 风险 / Trade-offs

| 风险 | 缓解 |
|---|---|
| `/dashboard/snapshot` 端点字段膨胀 | 限定字段集,V2 拆分;不引入 GraphQL |
| 三月均值在使用 < 3 月时不准 | 文案显示真实分母 "vs 近 N 月均值",N 来自真实有数据月数 |
| 6 月趋势循环 `compute_summary` 慢 | 监控 P95;若 > 200ms,改为一条 `GROUP BY (year, month)` 的 SQL |
| Postgres NULL 在 UNIQUE 中行为 | 用两个 partial unique index 兜底(见 4.2) |
| 时区跨月 0 点 | 前端用本地时区生成 `client_date` 一并传给后端;后端用 `client_date` 算 `is_current_month` / `day_of_month`,完全不调 `now()`;月窗口仍按 query `year+month` 算 `[YYYY-MM-01, 下月1日)`(纯日期,无时区) |
| 内联编辑触发整页 refetch 觉得卡 | 乐观更新 + 静默后台 mutate,UI 不显示 loading |
| 用户在父类设了预算又在子类设了 | 父类视作"独立的兄弟节点",不做自动汇总;V2 再考虑 |

---

## 9. 实施切片

| 切片 | 内容 | 验收 |
|---|---|---|
| **A. budgets 表 + CRUD API** | model + migration(含两个 partial unique index)+ `GET/PUT/DELETE /budgets` + `POST /budgets/copy-from` + 测试 | `pytest backend/tests/api/test_budgets.py` 全绿 |
| **B. dashboard snapshot API** | `services/dashboard.py` + `GET /dashboard/snapshot` + 测试 | snapshot 在 5 场景下输出正确;P95 < 300ms |
| **C. 前端 /dashboard 骨架 + 上半区** | 路由 + MonthPicker + BudgetSummaryCard + MonthPaceCard + CumulativeChart | 桌面 / 手机布局正常;loading / error 状态全 |
| **D. 类别列表 + 内联编辑 + 待办** | CategoryBudgetList + PendingActionsCard + budget-row-editor popover | 改预算后 UI 立即更新 + 刷新保留;待办 chip 跳转正确 |
| **E. 复盘区 + 设置页 + 移动端 polish + e2e** | CategoryDonut + MonthlyTrendBars + `/settings/budgets` + 2 条 e2e | 全设备截图人工对一遍;e2e 跑通 |

每切片可独立合并,后端切片 A/B 完成后,前端 C/D/E 可与他人并行。

---

## 10. 工作量估算

- 后端 A + B:**3 天**
- 前端 C:**2 天**
- 前端 D:**1.5 天**
- 前端 E + e2e:**1.5 天**
- 联调 + 视觉 polish:**1 天**
- **合计 ≈ 9 天**(单人节奏)

---

## 11. Open Questions

(目前为空,如设计实施过程中发现新问题,记录于此)
