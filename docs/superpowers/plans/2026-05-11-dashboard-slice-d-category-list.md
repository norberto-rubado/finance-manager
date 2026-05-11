# 切片 D:类别列表 + 内联编辑 + 待办 — 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL:Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec § 5.3 / 5.5 的中段:`<CategoryBudgetList>` + `<BudgetRowEditor>` Dialog 内联编辑 + `<PendingActionsCard>`,以及 `/settings/budgets` 完整设置页(含 `<CopyFromPrevButton>`)。

**Architecture:** 类别列表内嵌"调整"按钮,点开 shadcn `<Dialog>`(项目没有 popover,用 Dialog 等价),保存后乐观更新 + 静默重抓 snapshot。设置页是常规 CRUD 表格,使用现有 `<Card>` + `<Input>` 风格。

**Tech Stack:** 同切片 C(Next.js 14 / TypeScript / shadcn Dialog / Lucide / Vitest / RTL)。

---

## 依赖

- 切片 A + B + C 全部完成

## File Structure

**新建:**
```
frontend/
  app/(app)/settings/budgets/
    page.tsx                                # BudgetSettings
  components/
    dashboard/
      category-budget-list.tsx
      budget-row-editor.tsx                 # Dialog 形态
      pending-actions-card.tsx
    budgets/
      copy-from-prev-button.tsx
  tests/unit/
    progress-color.test.ts                  # 颜色阈值函数
    category-budget-list.test.tsx           # RTL:budget=null / 有 budget 两态
```

**修改:**
- `frontend/app/(app)/dashboard/page.tsx`:挂载 CategoryBudgetList + PendingActionsCard

---

## Task D1:进度条颜色函数 + 单测

**Files:**
- Create: `frontend/lib/utils/progress.ts`
- Create: `frontend/tests/unit/progress-color.test.ts`

- [ ] **Step 1.1:创建 `frontend/lib/utils/progress.ts`**

```typescript
/**
 * 类别预算进度条颜色阈值(spec § 5.5):
 *   ratio < 0.8 → emerald(还剩很多)
 *   0.8 <= ratio <= 1.0 → amber(吃紧)
 *   ratio > 1.0 → rose(超了)
 */
export type ProgressTone = 'safe' | 'warn' | 'danger';

export function progressTone(spent: number, budget: number): ProgressTone {
  if (budget <= 0) return 'safe';
  const r = spent / budget;
  if (r > 1) return 'danger';
  if (r >= 0.8) return 'warn';
  return 'safe';
}

export function progressBgClass(tone: ProgressTone): string {
  if (tone === 'danger') return 'bg-rose-500';
  if (tone === 'warn') return 'bg-amber-500';
  return 'bg-emerald-500';
}
```

- [ ] **Step 1.2:创建 `frontend/tests/unit/progress-color.test.ts`**

```typescript
import { describe, expect, it } from 'vitest';
import { progressBgClass, progressTone } from '@/lib/utils/progress';

describe('progressTone', () => {
  it('budget=0 时返回 safe(防 div0)', () => {
    expect(progressTone(100, 0)).toBe('safe');
  });
  it('70% → safe', () => {
    expect(progressTone(70, 100)).toBe('safe');
  });
  it('80% → warn', () => {
    expect(progressTone(80, 100)).toBe('warn');
  });
  it('100% → warn(边界包含)', () => {
    expect(progressTone(100, 100)).toBe('warn');
  });
  it('101% → danger', () => {
    expect(progressTone(101, 100)).toBe('danger');
  });
});

describe('progressBgClass', () => {
  it('映射到 tailwind 类', () => {
    expect(progressBgClass('safe')).toContain('emerald');
    expect(progressBgClass('warn')).toContain('amber');
    expect(progressBgClass('danger')).toContain('rose');
  });
});
```

- [ ] **Step 1.3:跑测试**

```bash
pnpm test:unit -- progress-color
```

期望:全 PASS。

- [ ] **Step 1.4:Commit**

```bash
git add frontend/lib/utils/progress.ts frontend/tests/unit/progress-color.test.ts
git commit -m "feat(utils): progress tone + bg color helpers"
```

---

## Task D2:`<BudgetRowEditor>` Dialog

**Files:**
- Create: `frontend/components/dashboard/budget-row-editor.tsx`

- [ ] **Step 2.1:创建 `budget-row-editor.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { upsertBudget } from '@/lib/api/budgets';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categoryId: number;
  categoryName: string;
  periodYear: number;
  periodMonth: number;
  /** 当前已有预算金额(没设传 null) */
  currentAmount: string | null;
  /** 当前 note */
  currentNote: string | null;
  /** 成功保存后回调 */
  onSaved: () => void;
}

export function BudgetRowEditor({
  open, onOpenChange, categoryId, categoryName,
  periodYear, periodMonth, currentAmount, currentNote, onSaved,
}: Props) {
  const [amount, setAmount] = useState<string>('');
  const [note, setNote] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);

  // open 切换时同步 props 到本地 state
  useEffect(() => {
    if (open) {
      setAmount(currentAmount ?? '');
      setNote(currentNote ?? '');
    }
  }, [open, currentAmount, currentNote]);

  async function onSave() {
    const num = Number(amount);
    if (!Number.isFinite(num) || num < 0) {
      toast.error('请输入有效金额(>= 0)');
      return;
    }
    setSubmitting(true);
    try {
      await upsertBudget({
        period_year: periodYear,
        period_month: periodMonth,
        category_id: categoryId,
        amount: amount,
        note: note.trim() === '' ? null : note,
      });
      toast.success('保存成功');
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error('保存失败:' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>调整预算 — {categoryName}</DialogTitle>
          <DialogDescription>
            {periodYear} 年 {periodMonth} 月。设置为 0 等于本月不限。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1">
            <Label htmlFor="budget-amount">金额(¥)</Label>
            <Input
              id="budget-amount"
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="例:1500"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="budget-note">备注(可选)</Label>
            <Textarea
              id="budget-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={200}
              placeholder="例:含外卖,不含周末聚餐"
              rows={2}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={onSave} disabled={submitting}>
            {submitting ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2.2:Commit**

```bash
git add frontend/components/dashboard/budget-row-editor.tsx
git commit -m "feat(dashboard): BudgetRowEditor Dialog for inline edit"
```

---

## Task D3:`<CategoryBudgetList>` 组件

**Files:**
- Create: `frontend/components/dashboard/category-budget-list.tsx`
- Create: `frontend/tests/unit/category-budget-list.test.tsx`

- [ ] **Step 3.1:创建 `category-budget-list.tsx`**

```tsx
'use client';

import { useState } from 'react';
import { Settings2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { fmtMoney } from '@/lib/utils/fmt';
import { progressBgClass, progressTone } from '@/lib/utils/progress';
import { BudgetRowEditor } from './budget-row-editor';
import type { SnapshotCategory } from '@/lib/api/types';

interface Props {
  categories: SnapshotCategory[];
  periodYear: number;
  periodMonth: number;
  editable: boolean;            // 非本月 → false
  onSaved: () => void;
}

export function CategoryBudgetList({
  categories, periodYear, periodMonth, editable, onSaved,
}: Props) {
  const [editing, setEditing] = useState<SnapshotCategory | null>(null);

  if (categories.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">类别预算</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">还没有支出类别</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">类别预算</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-border">
            {categories.map((c) => (
              <CategoryRow
                key={c.category_id}
                cat={c}
                editable={editable}
                onEdit={() => setEditing(c)}
              />
            ))}
          </ul>
        </CardContent>
      </Card>

      {editing && (
        <BudgetRowEditor
          open={editing !== null}
          onOpenChange={(o) => { if (!o) setEditing(null); }}
          categoryId={editing.category_id}
          categoryName={editing.name}
          periodYear={periodYear}
          periodMonth={periodMonth}
          currentAmount={editing.budget}
          currentNote={editing.note}
          onSaved={() => {
            setEditing(null);
            onSaved();
          }}
        />
      )}
    </>
  );
}

function CategoryRow({
  cat,
  editable,
  onEdit,
}: {
  cat: SnapshotCategory;
  editable: boolean;
  onEdit: () => void;
}) {
  const spent = Number(cat.spent);
  const budget = cat.budget === null ? null : Number(cat.budget);
  const avg = Number(cat.three_month_avg);

  const tone = budget === null ? 'safe' : progressTone(spent, budget);
  const ratio = budget === null || budget === 0 ? 0 : Math.min(spent / budget, 1.2);
  const bg = progressBgClass(tone);

  return (
    <li className="py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-sm font-medium" title={cat.note ?? undefined}>
              {cat.name}
            </span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {budget === null ? (
                <>
                  {fmtMoney(spent, { bare: true })}
                  <span className="ml-2">
                    vs 均{' '}
                    <span className={spent > avg ? 'text-rose-500' : 'text-emerald-500'}>
                      {fmtMoney(avg, { bare: true })} {spent > avg ? '↑' : '↓'}
                    </span>
                  </span>
                </>
              ) : (
                <>{fmtMoney(spent, { bare: true })} / {fmtMoney(budget, { bare: true })}</>
              )}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-muted">
            {budget === null ? (
              <div className="h-full w-full border-t border-dashed border-muted-foreground/50" />
            ) : (
              <div
                className={`h-full ${bg}`}
                style={{ width: `${ratio * 100}%` }}
                aria-label={`${cat.name} 已使用 ${Math.round(ratio * 100)}%`}
              />
            )}
          </div>
        </div>
        {editable && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onEdit}
            aria-label={`调整 ${cat.name} 预算`}
          >
            <Settings2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </li>
  );
}
```

- [ ] **Step 3.2:创建 RTL 测试 `category-budget-list.test.tsx`**

```typescript
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CategoryBudgetList } from '@/components/dashboard/category-budget-list';
import type { SnapshotCategory } from '@/lib/api/types';

function makeCat(overrides: Partial<SnapshotCategory>): SnapshotCategory {
  return {
    category_id: 1,
    name: '餐饮',
    icon: null,
    color: null,
    budget: null,
    spent: '0',
    three_month_avg: '0',
    note: null,
    is_overspending: false,
    ...overrides,
  };
}

describe('<CategoryBudgetList>', () => {
  it('类别预算未设时,显示 vs 均值', () => {
    const cats = [makeCat({ name: '餐饮', spent: '180', three_month_avg: '250' })];
    render(
      <CategoryBudgetList
        categories={cats}
        periodYear={2026}
        periodMonth={5}
        editable
        onSaved={() => {}}
      />,
    );
    expect(screen.getByText('餐饮')).toBeInTheDocument();
    expect(screen.getByText(/vs 均/)).toBeInTheDocument();
  });

  it('已设预算时,显示 spent / budget 格式', () => {
    const cats = [makeCat({
      name: '交通', spent: '320', budget: '1000', three_month_avg: '500',
    })];
    render(
      <CategoryBudgetList
        categories={cats}
        periodYear={2026}
        periodMonth={5}
        editable
        onSaved={() => {}}
      />,
    );
    // 数字会被 fmtMoney 格式化(带千分位),所以匹配子串
    expect(screen.getByText(/320/)).toBeInTheDocument();
    expect(screen.getByText(/1,000/)).toBeInTheDocument();
  });

  it('editable=false 时不渲染调整按钮', () => {
    const cats = [makeCat({ name: '餐饮' })];
    render(
      <CategoryBudgetList
        categories={cats}
        periodYear={2026}
        periodMonth={4}
        editable={false}
        onSaved={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: /调整/ })).toBeNull();
  });

  it('空数组时显示空态文案', () => {
    render(
      <CategoryBudgetList
        categories={[]}
        periodYear={2026}
        periodMonth={5}
        editable
        onSaved={() => {}}
      />,
    );
    expect(screen.getByText(/还没有支出类别/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3.3:跑测试**

```bash
pnpm test:unit -- category-budget-list
```

期望:4 个 test 全 PASS。

- [ ] **Step 3.4:Commit**

```bash
git add frontend/components/dashboard/category-budget-list.tsx frontend/tests/unit/category-budget-list.test.tsx
git commit -m "feat(dashboard): CategoryBudgetList with progress bars + RTL tests"
```

---

## Task D4:`<PendingActionsCard>` 组件

**Files:**
- Create: `frontend/components/dashboard/pending-actions-card.tsx`

- [ ] **Step 4.1:创建 `pending-actions-card.tsx`**

```tsx
'use client';

import Link from 'next/link';
import { AlertTriangle, Inbox, Search } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { SnapshotPending } from '@/lib/api/types';

interface Props {
  pending: SnapshotPending;
}

interface ChipProps {
  href: string;
  icon: React.ReactNode;
  label: string;
  count: number;
  tone: 'warning' | 'info' | 'neutral';
}

const TONE_CLASS: Record<ChipProps['tone'], string> = {
  warning: 'border-rose-500/40 bg-rose-500/10 text-rose-200',
  info: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  neutral: 'border-border bg-muted text-muted-foreground',
};

function Chip({ href, icon, label, count, tone }: ChipProps) {
  return (
    <Link
      href={href}
      className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2 transition-colors hover:opacity-90 ${TONE_CLASS[tone]}`}
    >
      <span className="flex items-center gap-2 text-sm">
        {icon}
        {label}
      </span>
      <span className="text-base font-semibold tabular-nums">{count}</span>
    </Link>
  );
}

export function PendingActionsCard({ pending }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">待处理</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Chip
          href="#category-budget-list"
          icon={<AlertTriangle className="h-4 w-4" />}
          label="超支类别"
          count={pending.overspending_count}
          tone={pending.overspending_count > 0 ? 'warning' : 'neutral'}
        />
        <Chip
          href="/transactions?category_id=null"
          icon={<Inbox className="h-4 w-4" />}
          label="未分类交易"
          count={pending.uncategorized_count}
          tone={pending.uncategorized_count > 0 ? 'info' : 'neutral'}
        />
        <Chip
          href="/statements"
          icon={<Search className="h-4 w-4" />}
          label="待审核去重"
          count={pending.dedup_pending_count}
          tone={pending.dedup_pending_count > 0 ? 'info' : 'neutral'}
        />
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4.2:Commit**

```bash
git add frontend/components/dashboard/pending-actions-card.tsx
git commit -m "feat(dashboard): PendingActionsCard with action chips"
```

---

## Task D5:把 CategoryBudgetList + PendingActions 挂到 `/dashboard`

**Files:**
- Modify: `frontend/app/(app)/dashboard/page.tsx`

- [ ] **Step 5.1:更新 `page.tsx`**

在 `<CumulativeChart>` 后面、文件末尾 comment 之前,加:

```tsx
import { CategoryBudgetList } from '@/components/dashboard/category-budget-list';
import { PendingActionsCard } from '@/components/dashboard/pending-actions-card';
```

(import 区,按字母序合并)

JSX 部分,把 `{/* 切片 D 在这下面会加 ... */}` 注释替换为:

```tsx
<div className="grid gap-4 lg:grid-cols-3">
  <div className="lg:col-span-2" id="category-budget-list">
    <CategoryBudgetList
      categories={snap.categories}
      periodYear={snap.period.year}
      periodMonth={snap.period.month}
      editable={snap.period.is_current_month}
      onSaved={() => setRefreshKey((k) => k + 1)}
    />
  </div>
  {snap.period.is_current_month && (
    <PendingActionsCard pending={snap.pending} />
  )}
</div>
```

- [ ] **Step 5.2:dev server 验证**

```bash
pnpm dev
```

打开 `http://localhost:3000/dashboard`:
- 在 CumulativeChart 下面看到类别列表(横向占 2/3)+ 待处理 chips(1/3)
- 切到上月 → 待处理 chips 整卡消失,类别列表的 ⚙ 按钮消失
- 点击某类别 ⚙ → Dialog 出现 → 输入金额 1500 → 保存 → toast 提示成功 → 进度条立即变化
- 刷新页面 → 改的预算仍保留

- [ ] **Step 5.3:typecheck + lint**

```bash
pnpm typecheck
pnpm lint
```

- [ ] **Step 5.4:Commit**

```bash
git add frontend/app/(app)/dashboard/page.tsx
git commit -m "feat(dashboard): wire CategoryBudgetList + PendingActions into page"
```

---

## Task D6:`<CopyFromPrevButton>` 组件

**Files:**
- Create: `frontend/components/budgets/copy-from-prev-button.tsx`

- [ ] **Step 6.1:创建 `copy-from-prev-button.tsx`**

```tsx
'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { copyBudgetsFrom } from '@/lib/api/budgets';
import { ApiClientError } from '@/lib/api/types';

interface Props {
  year: number;
  month: number;
  onSuccess: () => void;
}

/** 从上月复制预算。目标月已有数据时,后端返 409 → toast 提示先清空。 */
export function CopyFromPrevButton({ year, month, onSuccess }: Props) {
  const [busy, setBusy] = useState(false);

  function prevMonth(y: number, m: number): { year: number; month: number } {
    if (m === 1) return { year: y - 1, month: 12 };
    return { year: y, month: m - 1 };
  }

  async function onClick() {
    const prev = prevMonth(year, month);
    setBusy(true);
    try {
      const res = await copyBudgetsFrom({
        from_year: prev.year, from_month: prev.month,
        to_year: year, to_month: month,
      });
      if (res.length === 0) {
        toast.info('上月没有任何预算,不能复制');
      } else {
        toast.success(`已从 ${prev.year} 年 ${prev.month} 月复制 ${res.length} 条预算`);
        onSuccess();
      }
    } catch (e) {
      if (e instanceof ApiClientError && e.status === 409) {
        toast.error('当月已有预算,清空后再复制');
      } else {
        toast.error('复制失败:' + (e instanceof Error ? e.message : String(e)));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={busy}>
      <Copy className="mr-2 h-4 w-4" />
      {busy ? '复制中…' : '复制上月'}
    </Button>
  );
}
```

- [ ] **Step 6.2:Commit**

```bash
git add frontend/components/budgets/copy-from-prev-button.tsx
git commit -m "feat(budgets): CopyFromPrevButton with 409 handling"
```

---

## Task D7:`/settings/budgets` 设置页

**Files:**
- Create: `frontend/app/(app)/settings/budgets/page.tsx`

- [ ] **Step 7.1:创建 `page.tsx`**

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert } from '@/components/ui/alert';
import { ConfirmDialog } from '@/components/common/confirm-dialog';
import { CopyFromPrevButton } from '@/components/budgets/copy-from-prev-button';
import { MonthPicker, type MonthValue } from '@/components/dashboard/month-picker';
import { fmtMoney } from '@/lib/utils/fmt';

import { deleteBudget, listBudgets, upsertBudget } from '@/lib/api/budgets';
import { listCategories } from '@/lib/api/categories';
import type { BudgetOut, CategoryOut } from '@/lib/api/types';

export default function BudgetSettingsPage() {
  const [month, setMonth] = useState<MonthValue>(() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  });

  const [budgets, setBudgets] = useState<BudgetOut[] | null>(null);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const reload = useCallback(() => {
    setBudgets(null);
    Promise.all([
      listBudgets(month.year, month.month),
      listCategories().catch(() => ({ items: [], total: 0 })),
    ]).then(([bRes, cRes]) => {
      setBudgets(bRes);
      setCategories(cRes.items.filter((c) => c.kind === 'expense'));
    });
  }, [month]);

  useEffect(() => { reload(); }, [reload]);

  const budgetByCat = new Map<number | null, BudgetOut>();
  for (const b of budgets ?? []) {
    budgetByCat.set(b.category_id, b);
  }

  const total = budgetByCat.get(null);
  const sumCat = (budgets ?? [])
    .filter((b) => b.category_id !== null)
    .reduce((s, b) => s + Number(b.amount), 0);
  const exceedsTotal = total !== undefined && sumCat > Number(total.amount);

  async function onSave(catId: number | null, amount: string, note: string | null) {
    try {
      await upsertBudget({
        period_year: month.year,
        period_month: month.month,
        category_id: catId,
        amount,
        note,
      });
      toast.success('保存成功');
      reload();
    } catch (e) {
      toast.error('保存失败:' + (e instanceof Error ? e.message : String(e)));
    }
  }

  async function onDelete(id: number) {
    try {
      await deleteBudget(id);
      toast.success('已删除');
      reload();
    } catch (e) {
      toast.error('删除失败:' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setDeletingId(null);
    }
  }

  if (budgets === null) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">预算管理</h1>
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">预算管理</h1>
          <p className="text-sm text-muted-foreground">
            <Link className="underline" href="/settings">← 回到设置</Link> · 选择月份后设置总预算 + 各类别预算
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MonthPicker value={month} onChange={setMonth} />
          <CopyFromPrevButton
            year={month.year}
            month={month.month}
            onSuccess={reload}
          />
        </div>
      </div>

      {exceedsTotal && (
        <Alert variant="destructive">
          已设的类别预算总和 {fmtMoney(sumCat)} 已超过本月总预算 {fmtMoney(total!.amount)}。建议调整。
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>本月总预算</CardTitle>
        </CardHeader>
        <CardContent>
          <BudgetRow
            label="总预算"
            existing={total}
            onSave={(amt, note) => onSave(null, amt, note)}
            onDelete={total ? () => setDeletingId(total.id) : undefined}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>类别预算</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {categories.length === 0 ? (
            <p className="text-sm text-muted-foreground">还没有支出类别</p>
          ) : (
            categories.map((c) => (
              <BudgetRow
                key={c.id}
                label={c.name}
                existing={budgetByCat.get(c.id)}
                onSave={(amt, note) => onSave(c.id, amt, note)}
                onDelete={budgetByCat.has(c.id)
                  ? () => setDeletingId(budgetByCat.get(c.id)!.id)
                  : undefined}
              />
            ))
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deletingId !== null}
        onOpenChange={(o) => { if (!o) setDeletingId(null); }}
        title="确认删除预算?"
        description="删除后,该项预算会从本月移除;dashboard 上对应类别将回退到'vs 历史均值'参考。"
        confirmLabel="删除"
        onConfirm={() => deletingId !== null && onDelete(deletingId)}
      />
    </div>
  );
}

function BudgetRow({
  label, existing, onSave, onDelete,
}: {
  label: string;
  existing: BudgetOut | undefined;
  onSave: (amount: string, note: string | null) => void;
  onDelete?: () => void;
}) {
  const [amount, setAmount] = useState<string>(existing?.amount ?? '');
  const [note, setNote] = useState<string>(existing?.note ?? '');
  const [dirty, setDirty] = useState(false);

  // 切换月份后,existing 变了 → 同步本地 state
  useEffect(() => {
    setAmount(existing?.amount ?? '');
    setNote(existing?.note ?? '');
    setDirty(false);
  }, [existing]);

  return (
    <div className="grid grid-cols-1 gap-2 rounded-md border p-3 md:grid-cols-[1fr_auto_auto_auto]">
      <Label className="md:self-center">{label}</Label>
      <div className="space-y-1">
        <Input
          type="number"
          inputMode="decimal"
          step="0.01"
          min="0"
          value={amount}
          onChange={(e) => { setAmount(e.target.value); setDirty(true); }}
          placeholder="¥"
          className="w-32"
        />
      </div>
      <Textarea
        value={note}
        onChange={(e) => { setNote(e.target.value); setDirty(true); }}
        maxLength={200}
        placeholder="备注(可选)"
        rows={1}
        className="md:w-64"
      />
      <div className="flex items-center gap-1">
        <Button
          size="sm"
          disabled={!dirty || amount === ''}
          onClick={() => {
            onSave(amount, note.trim() === '' ? null : note);
            setDirty(false);
          }}
        >
          保存
        </Button>
        {onDelete && (
          <Button size="icon" variant="ghost" onClick={onDelete} aria-label="删除预算">
            <Trash2 className="h-4 w-4 text-rose-500" />
          </Button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 7.2:检查 `<Alert>` 是否支持 `variant="destructive"`**

```bash
cat frontend/components/ui/alert.tsx
```

如果不支持 destructive variant,在 `<Alert>` 用 className 覆盖:

```tsx
<Alert className="border-rose-500/40 bg-rose-500/10 text-rose-200">
  ...
</Alert>
```

- [ ] **Step 7.3:检查 `<ConfirmDialog>` 接口**

```bash
cat frontend/components/common/confirm-dialog.tsx
```

按现有签名调用;如果 prop 名不同(如 `onConfirm` vs `onOk`),按现有签名调整。

- [ ] **Step 7.4:dev 验证**

```bash
pnpm dev
```

- 访问 `/settings/budgets`
- 选择月份 → 列出"总预算"区 + 所有 expense 类别的预算行
- 设置一条总预算 ¥6000 → 保存 → 成功 toast
- 设置一条类别预算 ¥1500 → 保存 → 成功
- 类别预算之和 > 总预算时,顶部红条警告
- 点删除 → ConfirmDialog → 确认 → 删除
- 点"复制上月" → 提示已复制 / 没有上月数据 / 已有数据 409 三种情况
- 回到 `/dashboard` → 看到刚设的预算反映在环 + 类别列表里

- [ ] **Step 7.5:typecheck + lint**

```bash
pnpm typecheck
pnpm lint
```

期望:全绿。

- [ ] **Step 7.6:Commit**

```bash
git add frontend/app/(app)/settings/budgets/page.tsx
git commit -m "feat(settings): /settings/budgets full management page"
```

---

## Task D8:Settings 页加入口

**Files:**
- Modify: `frontend/app/(app)/settings/page.tsx`

- [ ] **Step 8.1:在 `/settings` 顶部加跳到预算管理的链接卡片**

打开 `frontend/app/(app)/settings/page.tsx`,在 `<ChangePasswordForm />` 上面或下面,加一张卡片:

```tsx
import Link from 'next/link';
import { Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';

// 在合适位置加:
<Card>
  <CardHeader>
    <CardTitle>预算管理</CardTitle>
    <CardDescription>设置月度总预算与各类别预算</CardDescription>
  </CardHeader>
  <CardContent>
    <Button asChild>
      <Link href="/settings/budgets">
        <Wallet className="mr-2 h-4 w-4" />
        管理预算
      </Link>
    </Button>
  </CardContent>
</Card>
```

- [ ] **Step 8.2:Commit**

```bash
git add frontend/app/(app)/settings/page.tsx
git commit -m "feat(settings): link to /settings/budgets"
```

---

## Task D9:综合验证

- [ ] **Step 9.1:跑所有 frontend 测试**

```bash
cd frontend
pnpm typecheck
pnpm lint
pnpm test:unit
```

期望:全绿。

- [ ] **Step 9.2:手动 verify(对照 overview 切片 D DoD)**

```bash
pnpm dev
```

逐条检查:
1. `/dashboard` 类别列表显示所有 expense 类别;有预算的彩色进度条、无预算的虚线 + "vs 均"
2. 点击 ⚙ → Dialog → 改预算 → 进度条立即更新
3. 点击"超支 chip" 锚定 `#category-budget-list`(页面滚动到列表);点"未分类 chip" 跳 `/transactions?category_id=null`;点"待审核" 跳 `/statements`
4. 进 `/settings/budgets` → 设置总预算 + 几个类别 → 回 `/dashboard` 看到变化
5. 切到上月 → 类别列表的 ⚙ 消失,待办卡消失

- [ ] **Step 9.3:Build 检查**

```bash
pnpm build
```

期望:build 通过。

- [ ] **Step 9.4:Commit polish(如有)**

---

## 切片 D 完成 DoD 复核

对照 [`2026-05-11-dashboard-overview.md`](2026-05-11-dashboard-overview.md) 切片 D 的 DoD:

- [x] `/dashboard` 类别列表显示所有 expense 类别;有预算的进度条带颜色;无预算的虚线 + "vs 均"
- [x] 点击类别行 ⚙ → Dialog 出现 amount + note → 保存 → 进度条立即更新
- [x] 点击"待办 chip"跳到对应页
- [x] `/settings/budgets` 页面可设置总预算 + 各类别预算 + note,可"复制上月"
- [x] RTL 单测覆盖:`<CategoryBudgetList>` budget=null / 有 budget 两态

切片 D 完成。下一步进入 [`2026-05-11-dashboard-slice-e-recap-polish.md`](2026-05-11-dashboard-slice-e-recap-polish.md)。
