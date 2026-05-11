# 切片 E:复盘区 + 移动端 + e2e — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec 剩余部分:`<CategoryDonut>` + `<MonthlyTrendBars>` 复盘组件、移动端 375 px 布局 polish、2 条 Playwright e2e(happy path + 时间窗切换)。

**Architecture:** Recharts `PieChart`(donut hole)+ `BarChart`。移动端通过 Tailwind 断点切换布局密度。e2e 复用现有 `tests/e2e/fixtures.ts` 的 `loggedIn` auto fixture。

**Tech Stack:** 同切片 C/D + Playwright 1.48。

---

## 依赖

- 切片 A + B + C + D 全部完成

## File Structure

**新建:**
```
frontend/
  components/dashboard/
    category-donut.tsx
    monthly-trend-bars.tsx
  tests/e2e/
    dashboard.spec.ts                        # 2 条 path
```

**修改:**
- `frontend/app/(app)/dashboard/page.tsx`:挂载 donut + trend
- `frontend/components/dashboard/category-budget-list.tsx`:移动端 Top 5 + 展开
- `frontend/components/dashboard/cumulative-chart.tsx`:手机端高度调整

---

## Task E1:`<CategoryDonut>` 组件

**Files:**
- Create: `frontend/components/dashboard/category-donut.tsx`

- [ ] **Step 1.1:创建 `category-donut.tsx`**

```tsx
'use client';

import { useMemo } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fmtMoney } from '@/lib/utils/fmt';
import type { SnapshotCategory } from '@/lib/api/types';

interface Props {
  categories: SnapshotCategory[];
}

const PALETTE = [
  'hsl(160 84% 39%)',   // emerald-600
  'hsl(217 91% 60%)',   // blue-500
  'hsl(38 92% 50%)',    // amber-500
  'hsl(280 65% 60%)',   // purple-500
  'hsl(0 84% 60%)',     // rose-500
  'hsl(195 53% 50%)',   // sky-500
];

interface Slice {
  name: string;
  value: number;
  color: string;
}

export function CategoryDonut({ categories }: Props) {
  const data = useMemo<Slice[]>(() => {
    const withSpent = categories
      .filter((c) => Number(c.spent) > 0)
      .map((c) => ({ name: c.name, value: Number(c.spent) }))
      .sort((a, b) => b.value - a.value);

    if (withSpent.length === 0) return [];

    const top5 = withSpent.slice(0, 5);
    const rest = withSpent.slice(5);
    const restSum = rest.reduce((s, x) => s + x.value, 0);

    const slices: Slice[] = top5.map((x, i) => ({
      name: x.name, value: x.value, color: PALETTE[i],
    }));
    if (restSum > 0) {
      slices.push({ name: '其他', value: restSum, color: PALETTE[5] });
    }
    return slices;
  }, [categories]);

  const total = data.reduce((s, x) => s + x.value, 0);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">分类占比</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            本月还没有支出
          </p>
        ) : (
          <div className="relative h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={2}
                  stroke="hsl(var(--background))"
                  strokeWidth={2}
                >
                  {data.map((s) => <Cell key={s.name} fill={s.color} />)}
                </Pie>
                <Tooltip
                  formatter={(value: number) => fmtMoney(value)}
                  contentStyle={{
                    background: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xs text-muted-foreground">本月总额</span>
              <span className="text-lg font-semibold tabular-nums">{fmtMoney(total)}</span>
            </div>
          </div>
        )}
        {data.length > 0 && (
          <ul className="mt-4 grid grid-cols-2 gap-1 text-xs">
            {data.map((s) => (
              <li key={s.name} className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-sm" style={{ background: s.color }} />
                <span className="truncate">{s.name}</span>
                <span className="ml-auto tabular-nums text-muted-foreground">
                  {((s.value / total) * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 1.2:Commit**

```bash
git add frontend/components/dashboard/category-donut.tsx
git commit -m "feat(dashboard): CategoryDonut with top-5 + others slice"
```

---

## Task E2:`<MonthlyTrendBars>` 组件

**Files:**
- Create: `frontend/components/dashboard/monthly-trend-bars.tsx`

- [ ] **Step 2.1:创建 `monthly-trend-bars.tsx`**

```tsx
'use client';

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fmtMoney } from '@/lib/utils/fmt';
import type { SnapshotTrendPoint } from '@/lib/api/types';

interface Props {
  points: SnapshotTrendPoint[];
  highlightYear: number;
  highlightMonth: number;
}

interface BarPoint {
  label: string;        // "5 月"
  year: number;
  month: number;
  expense: number;
  isHighlight: boolean;
}

export function MonthlyTrendBars({ points, highlightYear, highlightMonth }: Props) {
  const data: BarPoint[] = points.map((p) => ({
    label: `${p.month} 月`,
    year: p.year,
    month: p.month,
    expense: Number(p.expense),
    isHighlight: p.year === highlightYear && p.month === highlightMonth,
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">近 6 月支出趋势</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 12 }}
                className="fill-muted-foreground"
              />
              <YAxis
                tick={{ fontSize: 12 }}
                className="fill-muted-foreground"
                tickFormatter={(v: number) => fmtMoney(v, { bare: true })}
                width={64}
              />
              <Tooltip
                formatter={(value: number) => [fmtMoney(value), '支出']}
                labelFormatter={(label: string, payload) => {
                  if (payload && payload[0]) {
                    const p = payload[0].payload as BarPoint;
                    return `${p.year} 年 ${p.month} 月`;
                  }
                  return label;
                }}
                contentStyle={{
                  background: 'hsl(var(--popover))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="expense" radius={[4, 4, 0, 0]}>
                {data.map((d, i) => (
                  <Cell
                    key={i}
                    fill={d.isHighlight
                      ? 'hsl(var(--primary))'
                      : 'hsl(var(--muted-foreground) / 0.4)'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2.2:Commit**

```bash
git add frontend/components/dashboard/monthly-trend-bars.tsx
git commit -m "feat(dashboard): MonthlyTrendBars with current month highlight"
```

---

## Task E3:挂载到 `/dashboard` page

**Files:**
- Modify: `frontend/app/(app)/dashboard/page.tsx`

- [ ] **Step 3.1:在 `page.tsx` 添加 import**

```tsx
import { CategoryDonut } from '@/components/dashboard/category-donut';
import { MonthlyTrendBars } from '@/components/dashboard/monthly-trend-bars';
```

- [ ] **Step 3.2:替换文件末尾的 "切片 E 在这下面会加 ..." 注释**

把它替换为:

```tsx
<div className="grid gap-4 lg:grid-cols-2">
  <CategoryDonut categories={snap.categories} />
  <MonthlyTrendBars
    points={snap.monthly_trend}
    highlightYear={snap.period.year}
    highlightMonth={snap.period.month}
  />
</div>
```

- [ ] **Step 3.3:dev 验证**

```bash
pnpm dev
```

- 访问 `/dashboard` → 底部出现 Donut(本月分类占比)+ 6 月趋势柱(当月高亮)
- 切到上月 → Donut 显示上月数据;柱图把"上月"那根高亮

- [ ] **Step 3.4:Commit**

```bash
git add frontend/app/(app)/dashboard/page.tsx
git commit -m "feat(dashboard): wire Donut + TrendBars into page"
```

---

## Task E4:移动端 polish — 类别列表 Top 5 + 展开

**Files:**
- Modify: `frontend/components/dashboard/category-budget-list.tsx`

- [ ] **Step 4.1:在 `<CategoryBudgetList>` 加 `expanded` 内部 state**

打开 `frontend/components/dashboard/category-budget-list.tsx`,顶部 `useState` 区追加:

```tsx
const [expanded, setExpanded] = useState(false);
```

把列表渲染逻辑改为:

```tsx
const TOP_N = 5;
const visible = expanded ? categories : categories.slice(0, TOP_N);
const hasMore = categories.length > TOP_N;

return (
  <>
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">类别预算</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border">
          {visible.map((c) => (
            <CategoryRow
              key={c.category_id}
              cat={c}
              editable={editable}
              onEdit={() => setEditing(c)}
            />
          ))}
        </ul>
        {hasMore && (
          <div className="mt-2 flex justify-center md:hidden">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? '收起' : `展开全部(共 ${categories.length} 项)`}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
    {/* BudgetRowEditor 同切片 D */}
  </>
);
```

(注意:`md:hidden` 让"展开全部"按钮**只在手机端可见**;桌面端始终显示全部)

- [ ] **Step 4.2:`<CategoryRow>` 在手机端让整行可点击**

修改 `<CategoryRow>` 的 JSX:

```tsx
function CategoryRow(/* ...same props... */) {
  // 同上 spent / budget / tone / ratio / bg 计算

  return (
    <li>
      <button
        type="button"
        onClick={editable ? onEdit : undefined}
        disabled={!editable}
        className="flex w-full items-center justify-between gap-2 py-2 text-left disabled:cursor-default"
      >
        <div className="min-w-0 flex-1">
          {/* ... 原 label + 进度条 markup,保持不变 ... */}
        </div>
        {editable && (
          <Settings2 className="h-4 w-4 flex-shrink-0 text-muted-foreground md:text-foreground" />
        )}
      </button>
    </li>
  );
}
```

(手机端整行点击触发 onEdit,桌面端依然行内 ⚙ 图标视觉提示)

- [ ] **Step 4.3:`<CumulativeChart>` 手机端高度**

打开 `frontend/components/dashboard/cumulative-chart.tsx`,把 `<div className="h-64 w-full">` 改为:

```tsx
<div className="h-48 w-full md:h-64">
```

- [ ] **Step 4.4:dev 在手机模拟验证**

```bash
pnpm dev
```

F12 切手机模拟 375 × 667:
- 类别列表只显示前 5 项 + "展开全部" 按钮
- 点击任一类别行整行触发 Dialog(不再依赖小图标精准点击)
- 累计图高度变矮(更紧凑)
- Donut + Trend 自动堆叠成 1 列(因 `lg:grid-cols-2`)
- 整页不溢出

- [ ] **Step 4.5:Commit**

```bash
git add frontend/components/dashboard/category-budget-list.tsx frontend/components/dashboard/cumulative-chart.tsx
git commit -m "feat(dashboard): mobile polish (top 5 + row-tap + chart height)"
```

---

## Task E5:e2e path 1 — happy path

**Files:**
- Create: `frontend/tests/e2e/dashboard.spec.ts`

- [ ] **Step 5.1:创建 `dashboard.spec.ts` 的 path 1**

```typescript
import { test, expect } from './fixtures';

/**
 * Slice E e2e:dashboard 2 条核心 path。
 * 复用 fixtures.ts 的 loggedIn auto fixture。
 *
 * Path 1 — happy:进 dashboard → 改预算 → 数字变 → 刷新仍保留。
 * Path 2 — 时间窗:切到上月 → 月节奏卡消失 + 累计图变整月 + 待办卡消失。
 */

test.describe('Dashboard happy path', () => {
  test('进 /dashboard 改一个类别预算后,数字立即变 + 刷新保留', async ({ page }) => {
    // 1. 跳到 dashboard
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

    // 2. 等类别列表加载
    await expect(page.getByText('类别预算')).toBeVisible();

    // 3. 找一个"调整"按钮(任意类别均可,e2e 不挑特定类)
    const adjustButton = page.getByRole('button', { name: /^调整.*预算$/ }).first();
    await adjustButton.click();

    // 4. Dialog 出现
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText(/调整预算 —/)).toBeVisible();

    // 5. 输入金额(以 999 这个独特数字便于断言)
    const amountInput = page.getByLabel('金额(¥)');
    await amountInput.fill('999');

    // 6. 点保存
    await page.getByRole('button', { name: '保存' }).click();

    // 7. Dialog 关闭 + toast 出现
    await expect(page.getByRole('dialog')).not.toBeVisible();
    await expect(page.getByText('保存成功')).toBeVisible();

    // 8. 类别列表里出现 999(被 fmtMoney 格式化为 "999.00" 或 "¥999.00")
    await expect(page.getByText(/999/).first()).toBeVisible();

    // 9. 刷新,值仍保留
    await page.reload();
    await expect(page.getByText('类别预算')).toBeVisible();
    await expect(page.getByText(/999/).first()).toBeVisible();
  });
});
```

- [ ] **Step 5.2:跑 e2e path 1**

确保 backend + frontend dev server 都在跑(`docker-compose --profile dev up -d db` + 在 backend 跑 uvicorn + 在 frontend 跑 `pnpm dev`)。然后:

```bash
cd frontend
$env:ADMIN_TEST_PASSWORD = "<your-dev-password>"   # PowerShell
pnpm test:e2e -- dashboard.spec.ts -g "happy path"
```

期望:PASS。

如果失败:
- "找不到 ¥1500" → 看页面实际渲染的金额格式,调整 `getByText` 的正则
- "Dialog 不出现" → 确认前面切片 D 的 BudgetRowEditor 已实现
- "类别预算 heading 找不到" → 确认 snapshot 已加载,可能需要 `await page.waitForSelector` 等

---

## Task E6:e2e path 2 — 时间窗切换

**Files:**
- Modify: `frontend/tests/e2e/dashboard.spec.ts`

- [ ] **Step 6.1:在 `dashboard.spec.ts` 末尾追加 path 2**

```typescript
test.describe('Dashboard time-window switch', () => {
  test('切到上月 → 月节奏卡 + 待处理卡消失', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

    // 1. 验证本月时,节奏卡 + 待处理卡可见
    await expect(page.getByText('本月节奏')).toBeVisible();
    await expect(page.getByText('待处理')).toBeVisible();

    // 2. 打开 MonthPicker
    await page.getByRole('button', { name: '选择月份' }).click();

    // 3. 点击"上月"
    await page.getByRole('menuitem', { name: '上月' }).click();

    // 4. 等 URL 变化(出现 year/month)
    await page.waitForURL(/\/dashboard\?year=\d+&month=\d+/);

    // 5. 验证节奏卡 + 待处理卡消失(spec § 5.3)
    await expect(page.getByText('本月节奏')).not.toBeVisible();
    await expect(page.getByText('待处理')).not.toBeVisible();

    // 6. 累计支出图仍可见(变成整月)
    await expect(page.getByText('本月累计支出')).toBeVisible();

    // 7. 6 月趋势柱仍可见
    await expect(page.getByText('近 6 月支出趋势')).toBeVisible();
  });
});
```

- [ ] **Step 6.2:跑 e2e path 2**

```bash
pnpm test:e2e -- dashboard.spec.ts -g "time-window"
```

期望:PASS。

- [ ] **Step 6.3:跑两个 path 完整**

```bash
pnpm test:e2e -- dashboard.spec.ts
```

期望:2 个 test 都 PASS。

- [ ] **Step 6.4:Commit**

```bash
git add frontend/tests/e2e/dashboard.spec.ts
git commit -m "test(e2e): dashboard happy path + time-window switch"
```

---

## Task E7:整体视觉对一次(暗色 + 浅色)

**Files:**
- 无(只是手动 verify)

- [ ] **Step 7.1:启动 dev + 检查暗色模式**

```bash
pnpm dev
```

桌面 1440 × 900:
- `/dashboard` 整页应该:
  - 预算环颜色清晰(emerald / amber / rose 任一)
  - 累计图 area fill 半透明,预算斜线 amber 虚线
  - 类别进度条颜色饱和度适中
  - Donut slice 颜色对比明显(避免相邻色块过近)
  - Trend bars 当月高亮(primary 色)显著
  - 文字对比度足够(`text-muted-foreground` 不应难以阅读)

- [ ] **Step 7.2:切到浅色模式 + 检查**

点击右上角 ThemeToggle 切到 light:
- 整页背景白
- 卡片背景 / 边框可辨
- 进度条颜色仍可读
- 图表 grid line 可见但不抢戏

如果发现视觉问题(典型:某色块在 light 下接近背景),记录并调整对应 className。

- [ ] **Step 7.3:跑 Lighthouse 桌面(可选)**

```bash
pnpm exec lhci autorun --collect.url=http://localhost:3000/dashboard
```

(可选,只是用 Lighthouse 看一眼性能 + a11y)

如果不方便跑 Lighthouse,跳过。

- [ ] **Step 7.4:Commit 视觉 polish(若有)**

```bash
git add -A
git commit -m "chore(dashboard): visual polish for light/dark mode"
```

---

## Task E8:最终综合验证

- [ ] **Step 8.1:跑全部 frontend 验证**

```bash
cd frontend
pnpm typecheck
pnpm lint
pnpm test:unit
pnpm test:e2e
```

期望:全绿。

- [ ] **Step 8.2:Production build**

```bash
pnpm build
```

期望:无 warning,无 error。

- [ ] **Step 8.3:Backend 端综合**

```bash
cd ../backend
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check app
```

期望:全绿。

- [ ] **Step 8.4:整体端到端 smoke(对照 overview "完成 DoD")**

```bash
pnpm dev
```

逐条 verify:

**新用户路径(模拟全新账号)**
- 进 `/dashboard` 显示"未设总预算" + 类别走"vs 均"
- 点击"立即设置 →" 跳到 `/settings/budgets`
- 填总预算 ¥6000 + 餐饮 ¥1500 + 交通 ¥1000
- 回 `/dashboard` 看到预算环 ¥X/6000 + 餐饮 / 交通行有进度条

**日常监控路径**
- `/dashboard` 看到"本月已花 ¥X / ¥Y,节奏卡显示 提前/落后/正常"
- 类别超支 chip 显示数字 > 0 时,点击锚定到类别列表(页面滚到该位置)

**复盘路径**
- MonthPicker 切到上月 → 节奏卡 + 待办卡消失
- Donut 显示上月分类占比
- 6 月趋势柱图中"上月"那根高亮

如果任何一条不通,定位问题修复 + commit。

- [ ] **Step 8.5:最终 commit + 准备 PR**

```bash
git status
# 确认没有遗漏的 untracked / modified
git log --oneline 2026-05-11..HEAD    # 看本切片所有 commit
```

如果都干净,准备开 PR 或合并到主分支(按 user 习惯)。

---

## 切片 E 完成 DoD 复核

对照 [`2026-05-11-dashboard-overview.md`](2026-05-11-dashboard-overview.md) 切片 E 的 DoD:

- [x] `<CategoryDonut>` 显示本月 Top 5 + 其他;中心显示总额
- [x] `<MonthlyTrendBars>` 6 个月柱,当月高亮
- [x] 移动端 375 px:类别列表只显示 Top 5 + "展开全部";累计图高度 200 px;⚙ 按钮改为整行点击
- [x] Playwright 跑通 2 条 e2e
- [x] 暗 + 浅色模式视觉对一次

切片 E 完成。**整个 Dashboard + Budget 功能落地完成**。

---

## 后续 V2 可考虑(out of scope)

整体功能闭环后,如果想继续迭代:
- 年预算 / 周预算(扩 `budgets` 表加 `period_kind` 字段)
- 预算结转(carry over):月末未用完滚到下月
- 父子分类预算自动汇总
- 推送 / 邮件超支告警
- 月末花费预测(根据本月节奏外推)
- Dashboard 导出 PDF / 图片(月报)
- 类别细分维度(账户 × 类别交叉)

记录在 spec § 1.3 已经标为 out of scope,不在当前 9 天工作量内。
