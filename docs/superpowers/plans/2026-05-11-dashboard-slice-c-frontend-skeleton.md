# 切片 C:前端 /dashboard 骨架 + 上半区 — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 5 的前端骨架:`/dashboard` 路由 + MonthPicker + BudgetSummaryCard + MonthPaceCard + CumulativeChart 4 个组件。首页加跳转入口,Sidenav 加 Dashboard 导航项。

**Architecture:** Next.js 14 App Router,数据 fetch 走 `useEffect` 调 `getDashboardSnapshot()`,与现有 `transactions/page.tsx` 一致。配色全走 shadcn CSS variable,图表延续 `home/seven-day-chart.tsx` 的 Recharts 风格。

**Tech Stack:** Next.js 14 / React 18 / TypeScript 5.6 / shadcn/ui / Tailwind 3.4 / Recharts 2.13 / Lucide icons / Vitest 2.1 / Testing Library。

---

## 依赖

- 切片 B 完成(`GET /api/dashboard/snapshot` + `GET/PUT/DELETE /api/budgets` + `POST /api/budgets/copy-from` 全部 ready)

## File Structure

**新建:**
```
frontend/
  app/(app)/
    dashboard/
      page.tsx                              # DashboardPage(Suspense 入口 + 实际内容拆分)
  components/
    dashboard/
      month-picker.tsx
      budget-summary-card.tsx
      month-pace-card.tsx
      cumulative-chart.tsx
  lib/api/
    budgets.ts                              # listBudgets / upsertBudget / deleteBudget / copyBudgetsFrom
    dashboard.ts                            # getDashboardSnapshot
  tests/unit/
    dashboard-pace-text.test.ts             # pace 文案 + 颜色阈值
```

**修改:**
- `frontend/lib/api/types.ts`:加 budget + dashboard 相关 type
- `frontend/components/layout/sidenav.tsx`:加 Dashboard 导航项
- `frontend/app/page.tsx`:在 `<KpiCards>` 顶部加 "详查 →" 链接到 `/dashboard`

---

## Task C1:TS types

**Files:**
- Modify: `frontend/lib/api/types.ts`

- [ ] **Step 1.1:在 `frontend/lib/api/types.ts` 末尾追加 Budget 和 Dashboard types**

```typescript
// ============ Budget(切片 C) ============
export interface BudgetIn {
  period_year: number;
  period_month: number;
  category_id: number | null;   // null = 总预算
  amount: string;                // Decimal as string
  note: string | null;
}

export interface BudgetOut extends BudgetIn {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface BudgetCopyIn {
  from_year: number;
  from_month: number;
  to_year: number;
  to_month: number;
}

// ============ Dashboard Snapshot ============
export interface SnapshotPeriod {
  year: number;
  month: number;
  day_of_month: number;
  total_days: number;
  is_current_month: boolean;
}

export interface SnapshotTotal {
  budget: string | null;
  spent: string;
  income: string;
  prev_month_spent: string;
}

export interface SnapshotPace {
  expected_ratio: number;
  actual_ratio: number | null;
  delta_pct: number | null;
}

export interface SnapshotCategory {
  category_id: number;
  name: string;
  icon: string | null;
  color: string | null;
  budget: string | null;
  spent: string;
  three_month_avg: string;
  note: string | null;
  is_overspending: boolean;
}

export interface SnapshotTrendPoint {
  year: number;
  month: number;
  expense: string;
  income: string;
}

export interface SnapshotPending {
  uncategorized_count: number;
  dedup_pending_count: number;
  overspending_count: number;
}

export interface DashboardSnapshot {
  period: SnapshotPeriod;
  total: SnapshotTotal;
  pace: SnapshotPace;
  categories: SnapshotCategory[];
  monthly_trend: SnapshotTrendPoint[];
  pending: SnapshotPending;
}
```

- [ ] **Step 1.2:typecheck 通过**

```bash
cd frontend
pnpm typecheck
```

期望:无错误。

- [ ] **Step 1.3:Commit**

```bash
git add frontend/lib/api/types.ts
git commit -m "feat(frontend/types): add Budget + DashboardSnapshot types"
```

---

## Task C2:API client

**Files:**
- Create: `frontend/lib/api/budgets.ts`
- Create: `frontend/lib/api/dashboard.ts`

- [ ] **Step 2.1:创建 `frontend/lib/api/budgets.ts`**

```typescript
import { apiFetch } from './client';
import type { BudgetCopyIn, BudgetIn, BudgetOut } from './types';

export function listBudgets(year: number, month: number): Promise<BudgetOut[]> {
  return apiFetch<BudgetOut[]>('/budgets', { query: { year, month } });
}

export function upsertBudget(body: BudgetIn): Promise<BudgetOut> {
  return apiFetch<BudgetOut>('/budgets', { method: 'PUT', body });
}

export function deleteBudget(id: number): Promise<void> {
  return apiFetch<void>(`/budgets/${id}`, { method: 'DELETE' });
}

export function copyBudgetsFrom(body: BudgetCopyIn): Promise<BudgetOut[]> {
  return apiFetch<BudgetOut[]>('/budgets/copy-from', { method: 'POST', body });
}
```

- [ ] **Step 2.2:创建 `frontend/lib/api/dashboard.ts`**

```typescript
import { apiFetch } from './client';
import type { DashboardSnapshot } from './types';

/** client_date 必传:YYYY-MM-DD 格式的本地时区"今天"。 */
export function getDashboardSnapshot(
  year: number,
  month: number,
  clientDate: string,
): Promise<DashboardSnapshot> {
  return apiFetch<DashboardSnapshot>('/dashboard/snapshot', {
    query: { year, month, client_date: clientDate },
  });
}
```

- [ ] **Step 2.3:typecheck**

```bash
pnpm typecheck
```

期望:无错误。

- [ ] **Step 2.4:Commit**

```bash
git add frontend/lib/api/budgets.ts frontend/lib/api/dashboard.ts
git commit -m "feat(frontend/api): budgets + dashboard API clients"
```

---

## Task C3:`<MonthPicker>` 组件

**Files:**
- Create: `frontend/components/dashboard/month-picker.tsx`

- [ ] **Step 3.1:创建 `month-picker.tsx`**

```tsx
'use client';

import { useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

export interface MonthValue {
  year: number;
  month: number;   // 1..12
}

interface Props {
  value: MonthValue;
  onChange: (v: MonthValue) => void;
  /** 从今天往前能选多少个月(含本月),默认 12 */
  monthsBack?: number;
}

/** 返回 (year, month) 加减 delta 月。 */
function shiftMonth(year: number, month: number, delta: number): MonthValue {
  const total = year * 12 + (month - 1) + delta;
  return { year: Math.floor(total / 12), month: (total % 12) + 1 };
}

function labelFor(v: MonthValue, today: MonthValue): string {
  if (v.year === today.year && v.month === today.month) return '本月';
  const last = shiftMonth(today.year, today.month, -1);
  if (v.year === last.year && v.month === last.month) return '上月';
  return `${v.year} 年 ${v.month} 月`;
}

export function MonthPicker({ value, onChange, monthsBack = 12 }: Props) {
  const today = useMemo<MonthValue>(() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  }, []);

  const options = useMemo<MonthValue[]>(() => {
    const arr: MonthValue[] = [];
    for (let i = 0; i < monthsBack; i++) {
      arr.push(shiftMonth(today.year, today.month, -i));
    }
    return arr;
  }, [today, monthsBack]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" aria-label="选择月份">
          {labelFor(value, today)}
          <ChevronDown className="ml-2 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {options.map((o) => (
          <DropdownMenuItem
            key={`${o.year}-${o.month}`}
            onSelect={() => onChange(o)}
          >
            {labelFor(o, today)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 3.2:Commit**

```bash
git add frontend/components/dashboard/month-picker.tsx
git commit -m "feat(dashboard): MonthPicker component"
```

---

## Task C4:`<BudgetSummaryCard>` 组件

**Files:**
- Create: `frontend/components/dashboard/budget-summary-card.tsx`

- [ ] **Step 4.1:创建 `budget-summary-card.tsx`**

```tsx
'use client';

import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { fmtMoney } from '@/lib/utils/fmt';
import type { SnapshotTotal, SnapshotPace } from '@/lib/api/types';

interface Props {
  total: SnapshotTotal;
  pace: SnapshotPace;
}

/** 进度条颜色阈值。actual_ratio = spent/budget。 */
function ringColor(ratio: number): string {
  if (ratio > 1) return 'hsl(0 84% 60%)';        // rose-500
  if (ratio > 0.8) return 'hsl(38 92% 50%)';     // amber-500
  return 'hsl(160 84% 39%)';                     // emerald-500
}

export function BudgetSummaryCard({ total, pace }: Props) {
  const budget = total.budget === null ? null : Number(total.budget);
  const spent = Number(total.spent);

  if (budget === null) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-3 py-10">
          <div className="text-sm text-muted-foreground">未设总预算</div>
          <div className="text-2xl font-semibold tabular-nums">{fmtMoney(spent)}</div>
          <div className="text-xs text-muted-foreground">本月已花</div>
          <Button asChild size="sm">
            <Link href="/settings/budgets">立即设置 →</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const ratio = pace.actual_ratio ?? 0;
  const clamped = Math.min(Math.max(ratio, 0), 1.2); // 视觉上限 120%
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped);
  const remaining = budget - spent;

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 py-6">
        <svg width="160" height="160" viewBox="0 0 160 160" aria-label="预算环">
          <circle
            cx="80" cy="80" r={radius}
            fill="none" stroke="hsl(var(--muted))" strokeWidth="12"
          />
          <circle
            cx="80" cy="80" r={radius}
            fill="none" stroke={ringColor(ratio)} strokeWidth="12"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            transform="rotate(-90 80 80)"
          />
          <text x="80" y="76" textAnchor="middle" className="fill-foreground"
                style={{ font: '600 22px var(--font-inter)' }}>
            {Math.round(ratio * 100)}%
          </text>
          <text x="80" y="98" textAnchor="middle" className="fill-muted-foreground"
                style={{ font: '12px var(--font-inter)' }}>
            {fmtMoney(spent, { bare: true })} / {fmtMoney(budget, { bare: true })}
          </text>
        </svg>
        <div className="text-sm">
          剩余 <span className="font-medium tabular-nums">{fmtMoney(remaining)}</span>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/settings/budgets">管理预算</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4.2:Commit**

```bash
git add frontend/components/dashboard/budget-summary-card.tsx
git commit -m "feat(dashboard): BudgetSummaryCard with SVG ring"
```

---

## Task C5:`<MonthPaceCard>` 组件

**Files:**
- Create: `frontend/components/dashboard/month-pace-card.tsx`

- [ ] **Step 5.1:创建 `month-pace-card.tsx`**

```tsx
'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fmtMoney, fmtPercent } from '@/lib/utils/fmt';
import type { SnapshotPace, SnapshotPeriod, SnapshotTotal } from '@/lib/api/types';

interface Props {
  period: SnapshotPeriod;
  total: SnapshotTotal;
  pace: SnapshotPace;
}

/** 节奏文案:
 *  delta_pct > 10 → "提前 N%"(rose 调)
 *  delta_pct < -10 → "落后 N%"(emerald 调)
 *  否则 → "正常节奏"
 */
function paceDescriptor(delta: number | null): { text: string; tone: string } {
  if (delta === null) return { text: '—', tone: 'text-muted-foreground' };
  if (delta > 10) return { text: `提前 ${delta.toFixed(0)}%`, tone: 'text-rose-500' };
  if (delta < -10) return { text: `落后 ${Math.abs(delta).toFixed(0)}%`, tone: 'text-emerald-500' };
  return { text: '正常节奏', tone: 'text-foreground' };
}

export function MonthPaceCard({ period, total, pace }: Props) {
  const desc = paceDescriptor(pace.delta_pct);

  const prevSpent = Number(total.prev_month_spent);
  const thisSpent = Number(total.spent);
  let vsPrev: { text: string; tone: string };
  if (prevSpent === 0) {
    vsPrev = { text: '—', tone: 'text-muted-foreground' };
  } else {
    const pct = (thisSpent - prevSpent) / prevSpent * 100;
    if (pct > 0) {
      vsPrev = { text: `↑ ${pct.toFixed(0)}%`, tone: 'text-rose-500' };
    } else if (pct < 0) {
      vsPrev = { text: `↓ ${Math.abs(pct).toFixed(0)}%`, tone: 'text-emerald-500' };
    } else {
      vsPrev = { text: '持平', tone: 'text-muted-foreground' };
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">本月节奏</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4">
          <div>
            <dt className="text-xs text-muted-foreground">月进度</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">
              第 {period.day_of_month}/{period.total_days} 天
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">应该花</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">
              {fmtPercent(pace.expected_ratio, 0)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">节奏</dt>
            <dd className={`mt-1 text-lg font-semibold ${desc.tone}`}>
              {desc.text}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">vs 上月</dt>
            <dd className={`mt-1 text-lg font-semibold ${vsPrev.tone}`}>
              {vsPrev.text}
            </dd>
          </div>
        </dl>
        <div className="mt-3 text-xs text-muted-foreground">
          上月支出 {fmtMoney(prevSpent)}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 5.2:写 paceDescriptor 单元测试**

创建 `frontend/tests/unit/dashboard-pace-text.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

// 把 paceDescriptor 从 month-pace-card 中独立出来以便测试,
// 或者用 export const paceDescriptor = ... 直接 import。
import { paceDescriptor } from '@/components/dashboard/month-pace-card';

describe('paceDescriptor', () => {
  it('null delta → 占位', () => {
    expect(paceDescriptor(null).text).toBe('—');
  });
  it('+15% → 提前(rose)', () => {
    const r = paceDescriptor(15);
    expect(r.text).toContain('提前');
    expect(r.tone).toContain('rose');
  });
  it('-15% → 落后(emerald)', () => {
    const r = paceDescriptor(-15);
    expect(r.text).toContain('落后');
    expect(r.tone).toContain('emerald');
  });
  it('±10% 以内 → 正常', () => {
    expect(paceDescriptor(5).text).toBe('正常节奏');
    expect(paceDescriptor(-5).text).toBe('正常节奏');
  });
});
```

回到 `month-pace-card.tsx`,把 `paceDescriptor` 改成 `export`:

```tsx
export function paceDescriptor(delta: number | null): { text: string; tone: string } {
  // ... 同上
}
```

- [ ] **Step 5.3:跑测试**

```bash
pnpm test:unit -- dashboard-pace-text
```

期望:4 个 test 全 PASS。

- [ ] **Step 5.4:Commit**

```bash
git add frontend/components/dashboard/month-pace-card.tsx frontend/tests/unit/dashboard-pace-text.test.ts
git commit -m "feat(dashboard): MonthPaceCard with pace descriptor + tests"
```

---

## Task C6:`<CumulativeChart>` 组件

**Files:**
- Create: `frontend/components/dashboard/cumulative-chart.tsx`

**说明:**这个组件单独 fetch 当月 transactions(类似 `home/seven-day-chart.tsx`),客户端按日累加。Snapshot 端点不含 daily breakdown,沿用现有模式。

- [ ] **Step 6.1:创建 `cumulative-chart.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { listTransactions } from '@/lib/api/transactions';
import { fmtMoney } from '@/lib/utils/fmt';

interface Props {
  year: number;
  month: number;
  totalDays: number;
  dayOfMonth: number;          // 本月画到 dayOfMonth,非本月画到 totalDays
  isCurrentMonth: boolean;
  budget: string | null;       // 总预算,用于画斜线
}

interface DayPoint {
  day: number;
  cumulative: number;          // 累计支出
  budgetLine: number | null;   // 预算斜线值 = budget * day / totalDays
}

export function CumulativeChart({
  year, month, totalDays, dayOfMonth, isCurrentMonth, budget,
}: Props) {
  const [points, setPoints] = useState<DayPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const start = new Date(year, month - 1, 1);
    const endDay = isCurrentMonth ? dayOfMonth : totalDays;
    const end = new Date(year, month - 1, endDay + 1);  // [start, end)

    listTransactions({
      date_from: start.toISOString(),
      date_to: end.toISOString(),
      limit: 1000,
      is_mirror: false,
      kind: 'expense',
    })
      .then((res) => {
        // 按 day-of-month 桶累加
        const dailySpend = new Array(endDay + 1).fill(0);  // index 1..endDay
        for (const t of res.items) {
          const d = new Date(t.tx_time).getDate();
          if (d >= 1 && d <= endDay) {
            dailySpend[d] += Math.abs(Number(t.amount));
          }
        }
        // 累计
        const budgetNum = budget === null ? null : Number(budget);
        const arr: DayPoint[] = [];
        let cum = 0;
        for (let d = 1; d <= endDay; d++) {
          cum += dailySpend[d];
          arr.push({
            day: d,
            cumulative: cum,
            budgetLine: budgetNum === null ? null : budgetNum * d / totalDays,
          });
        }
        setPoints(arr);
      })
      .catch((e: Error) => setError(e.message));
  }, [year, month, totalDays, dayOfMonth, isCurrentMonth, budget]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">本月累计支出</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-destructive">加载失败:{error}</p>
        ) : points === null ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="day"
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
                  formatter={(value: number, name: string) => {
                    if (name === 'cumulative') return [fmtMoney(value), '累计支出'];
                    if (name === 'budgetLine') return [fmtMoney(value), '预算线'];
                    return [String(value), name];
                  }}
                  labelFormatter={(d: number) => `第 ${d} 天`}
                  contentStyle={{
                    background: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="cumulative"
                  stroke="hsl(var(--primary))"
                  fill="hsl(var(--primary))"
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
                {budget !== null && (
                  <Line
                    type="linear"
                    dataKey="budgetLine"
                    stroke="hsl(38 92% 50%)"
                    strokeDasharray="4 4"
                    strokeWidth={1.5}
                    dot={false}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 6.2:Commit**

```bash
git add frontend/components/dashboard/cumulative-chart.tsx
git commit -m "feat(dashboard): CumulativeChart with budget reference line"
```

---

## Task C7:`/dashboard` 路由 page

**Files:**
- Create: `frontend/app/(app)/dashboard/page.tsx`

- [ ] **Step 7.1:创建 `page.tsx`**

```tsx
'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { EmptyState } from '@/components/common/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { MonthPicker, type MonthValue } from '@/components/dashboard/month-picker';
import { BudgetSummaryCard } from '@/components/dashboard/budget-summary-card';
import { MonthPaceCard } from '@/components/dashboard/month-pace-card';
import { CumulativeChart } from '@/components/dashboard/cumulative-chart';
import { getDashboardSnapshot } from '@/lib/api/dashboard';
import type { DashboardSnapshot } from '@/lib/api/types';

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardView />
    </Suspense>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-64 w-full" />
        ))}
      </div>
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function todayLocal(): { value: MonthValue; iso: string } {
  const d = new Date();
  const year = d.getFullYear();
  const month = d.getMonth() + 1;
  const day = String(d.getDate()).padStart(2, '0');
  return {
    value: { year, month },
    iso: `${year}-${String(month).padStart(2, '0')}-${day}`,
  };
}

function DashboardView() {
  const router = useRouter();
  const sp = useSearchParams();

  // URL → MonthValue;无 query 时用本地"今天",并立即 router.replace 同步
  const today = useMemo(() => todayLocal(), []);
  const urlYear = sp.get('year');
  const urlMonth = sp.get('month');

  useEffect(() => {
    if (urlYear === null || urlMonth === null) {
      const search = new URLSearchParams();
      search.set('year', String(today.value.year));
      search.set('month', String(today.value.month));
      router.replace(`/dashboard?${search.toString()}`);
    }
  }, [urlYear, urlMonth, today, router]);

  const month: MonthValue = useMemo(() => {
    if (urlYear !== null && urlMonth !== null) {
      return { year: Number(urlYear), month: Number(urlMonth) };
    }
    return today.value;
  }, [urlYear, urlMonth, today]);

  const [snap, setSnap] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // 拉 snapshot
  const fetchSnap = useCallback(() => {
    setError(null);
    setSnap(null);
    getDashboardSnapshot(month.year, month.month, today.iso)
      .then(setSnap)
      .catch((e: Error) => setError(e.message));
  }, [month.year, month.month, today.iso]);

  useEffect(() => {
    fetchSnap();
  }, [fetchSnap, refreshKey]);

  const onMonthChange = (v: MonthValue) => {
    const search = new URLSearchParams();
    search.set('year', String(v.year));
    search.set('month', String(v.month));
    router.push(`/dashboard?${search.toString()}`);
  };

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <EmptyState
          title="加载失败"
          description={error}
          action={
            <Button onClick={() => setRefreshKey((k) => k + 1)}>重试</Button>
          }
        />
      </div>
    );
  }

  if (snap === null) {
    return <DashboardSkeleton />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <MonthPicker value={month} onChange={onMonthChange} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <BudgetSummaryCard total={snap.total} pace={snap.pace} />
        {snap.period.is_current_month && (
          <MonthPaceCard period={snap.period} total={snap.total} pace={snap.pace} />
        )}
      </div>

      <CumulativeChart
        year={snap.period.year}
        month={snap.period.month}
        totalDays={snap.period.total_days}
        dayOfMonth={snap.period.day_of_month}
        isCurrentMonth={snap.period.is_current_month}
        budget={snap.total.budget}
      />

      {/* 切片 D 在这下面会加 <CategoryBudgetList> + <PendingActionsCard> */}
      {/* 切片 E 在这下面会加 <CategoryDonut> + <MonthlyTrendBars> */}
    </div>
  );
}
```

- [ ] **Step 7.2:验证 `<EmptyState>` 支持 `action` prop**

```bash
cat frontend/components/common/empty-state.tsx
```

如果现有 `<EmptyState>` 没 `action` prop,稍微改一下:

```tsx
// frontend/components/common/empty-state.tsx
interface Props {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-md border border-dashed py-12">
      <div className="text-base font-medium">{title}</div>
      {description && <div className="text-sm text-muted-foreground">{description}</div>}
      {action}
    </div>
  );
}
```

(如果已经支持就跳过此 step)

- [ ] **Step 7.3:本地启动 dev server 验证**

```bash
cd frontend
pnpm dev
```

打开 `http://localhost:3000/dashboard`:
- 期望:看到顶部 "Dashboard" 标题 + MonthPicker(显示"本月")+ BudgetSummaryCard + MonthPaceCard + CumulativeChart 三个区
- 点击 MonthPicker 选"上月" → URL 变成 `?year=...&month=...`,MonthPaceCard 消失,CumulativeChart 重新加载
- 网络断开重试时显示 EmptyState

- [ ] **Step 7.4:typecheck + lint**

```bash
pnpm typecheck
pnpm lint
```

期望:全绿。

- [ ] **Step 7.5:Commit**

```bash
git add frontend/app/(app)/dashboard/page.tsx
# 如果 Step 7.2 改了 EmptyState
git add frontend/components/common/empty-state.tsx
git commit -m "feat(dashboard): /dashboard route with snapshot fetch + skeleton + error states"
```

---

## Task C8:Sidenav 加 Dashboard + 首页加详查入口

**Files:**
- Modify: `frontend/components/layout/sidenav.tsx`
- Modify: `frontend/components/layout/tabbar.tsx`(若移动端 tabbar 也用导航数组)
- Modify: `frontend/app/page.tsx`

- [ ] **Step 8.1:在 `sidenav.tsx` 的 `NAV` 数组里加 Dashboard 项**

打开 `frontend/components/layout/sidenav.tsx`,在 `NAV` 数组的 "首页" 后面加:

```typescript
import { LayoutDashboard } from 'lucide-react';

const NAV = [
  { href: '/', label: '首页', icon: Home },
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/transactions', label: '交易', icon: ListOrdered },
  // ... 其余不变
] as const;
```

- [ ] **Step 8.2:检查 `tabbar.tsx` 是否需要同步**

```bash
cat frontend/components/layout/tabbar.tsx
```

如果 tabbar 也用同样的 NAV(导出自 sidenav 或独立硬编码),同步加 Dashboard 项;手机底部 tabbar 最多 5 项,优先级 = 首页 > Dashboard > 交易 > 导入 > 设置(占满 5 个)。

如果当前 tabbar 已经 5 项,要把"设置"挤掉(移到"更多"汉堡菜单);若工时紧,先**保持 tabbar 不变**,只在 sidenav 加 Dashboard,移动端用户用顶部菜单进入。本 step 默认采用"sidenav 加 + tabbar 不动"的最小改动方案。

- [ ] **Step 8.3:在首页 `<KpiCards>` 旁边加"详查 →"链接**

打开 `frontend/app/page.tsx`,改 h1 行:

```tsx
import Link from 'next/link';
import { Shell } from '@/components/layout/shell';
import { Button } from '@/components/ui/button';
import { KpiCards } from '@/components/home/kpi-cards';
import { RecentList } from '@/components/home/recent-list';
import { SevenDayChart } from '@/components/home/seven-day-chart';

export default function HomePage() {
  return (
    <Shell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">本月概览</h1>
          <Button asChild variant="ghost" size="sm">
            <Link href="/dashboard">详查 →</Link>
          </Button>
        </div>
        <KpiCards />
        <div className="grid gap-4 lg:grid-cols-2">
          <RecentList />
          <SevenDayChart />
        </div>
      </div>
    </Shell>
  );
}
```

- [ ] **Step 8.4:本地验证**

```bash
pnpm dev
```

- 访问 `/`:右上角看到 "详查 →"
- 点击 → 跳到 `/dashboard`
- 侧栏看到 Dashboard 项(桌面端);active 高亮在 Dashboard 上

- [ ] **Step 8.5:Commit**

```bash
git add frontend/components/layout/sidenav.tsx frontend/app/page.tsx
git commit -m "feat(nav): add Dashboard to sidenav and link from home page"
```

---

## Task C9:综合验证

- [ ] **Step 9.1:跑 typecheck + lint + unit**

```bash
cd frontend
pnpm typecheck
pnpm lint
pnpm test:unit
```

期望:全绿。

- [ ] **Step 9.2:dev server 手动 verify(参照 overview 切片 C DoD)**

```bash
pnpm dev
```

逐条检查:
1. `http://localhost:3000/dashboard` 看到顶部 MonthPicker(默认本月)、预算环(未设时显示"未设总预算 [立即设置 →]")、节奏卡、累计曲线
2. MonthPicker 切换到上月 → URL 同步、数据重新加载、节奏卡消失、累计图变整月
3. 把 backend 关掉重试 → 看到 EmptyState 红字 + Retry 按钮;启 backend → 点 Retry → 数据回来
4. F12 切到手机模拟 375 × 667 → 上半区单列,不溢出
5. 首页 `/` 右上角"详查 →"链接,点击跳 `/dashboard`

如果有视觉问题(如环颜色在 dark mode 太暗,字号偏小),做最小调整。

- [ ] **Step 9.3:Build 检查**

```bash
pnpm build
```

期望:build 通过,无 SSR/CSR warning。

如果出现 `useSearchParams() should be wrapped in a suspense boundary`,确认 `DashboardPage` 已经把 `DashboardView` 包在 `<Suspense>` 内(Step 7.1 已经这么写)。

- [ ] **Step 9.4:Commit 最终 polish(如有)**

```bash
git add -A
git commit -m "chore(dashboard): slice C polish + verify"
```

---

## 切片 C 完成 DoD 复核

对照 [`2026-05-11-dashboard-overview.md`](2026-05-11-dashboard-overview.md) 切片 C 的 DoD:

- [x] `/dashboard` 看到 MonthPicker + 预算环 + 节奏卡 + 累计图
- [x] MonthPicker 切换上月 → URL 同步 + 数据刷新 + 节奏卡消失
- [x] 网络断 → EmptyState + Retry
- [x] 手机 375px 单列布局不溢出
- [x] 首页加"详查 →"链接

切片 C 完成。下一步进入 [`2026-05-11-dashboard-slice-d-category-list.md`](2026-05-11-dashboard-slice-d-category-list.md)。
