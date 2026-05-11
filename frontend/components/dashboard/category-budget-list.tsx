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
  editable: boolean; // 非本月 → false
  onSaved: () => void;
}

const TOP_N = 5;

export function CategoryBudgetList({
  categories,
  periodYear,
  periodMonth,
  editable,
  onSaved,
}: Props) {
  const [editing, setEditing] = useState<SnapshotCategory | null>(null);
  const [expanded, setExpanded] = useState(false);

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

  // 手机端只显示 Top N(`md:hidden` 控制 expand 按钮可见性);
  // 桌面端始终显示全部:用 CSS `md:!flex` / `md:!list-item` 处理被折叠的行,
  // 这里直接给 visible/hidden 行打 class,避免维护两套列表。
  const hasMore = categories.length > TOP_N;

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">类别预算</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-border">
            {categories.map((c, i) => {
              const beyondTop = i >= TOP_N;
              // 桌面端永远显示;手机端在未展开时隐藏超出 TOP_N 的行
              const hiddenOnMobile = beyondTop && !expanded;
              return (
                <CategoryRow
                  key={c.category_id}
                  cat={c}
                  editable={editable}
                  hiddenOnMobile={hiddenOnMobile}
                  onEdit={() => setEditing(c)}
                />
              );
            })}
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

      {editing && (
        <BudgetRowEditor
          open={editing !== null}
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
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
  hiddenOnMobile,
  onEdit,
}: {
  cat: SnapshotCategory;
  editable: boolean;
  hiddenOnMobile: boolean;
  onEdit: () => void;
}) {
  const spent = Number(cat.spent);
  const budget = cat.budget === null ? null : Number(cat.budget);
  const avg = Number(cat.three_month_avg);

  const tone = budget === null ? 'safe' : progressTone(spent, budget);
  const ratio = budget === null || budget === 0 ? 0 : Math.min(spent / budget, 1.2);
  const bg = progressBgClass(tone);

  // 整行点击触发 onEdit(手机端不再依赖小图标精准点击)。
  // editable=false 时整行为静态 div,无 button role,以保证桌面端
  // 历史月份(非 editable)既无 ⚙ 也无点击反馈。
  const inner = (
    <>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span
            className="truncate text-sm font-medium"
            title={cat.note ?? undefined}
          >
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
              <>
                {fmtMoney(spent, { bare: true })} /{' '}
                {fmtMoney(budget, { bare: true })}
              </>
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
        <Settings2 className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
      )}
    </>
  );

  return (
    <li className={hiddenOnMobile ? 'hidden md:list-item' : undefined}>
      {editable ? (
        <button
          type="button"
          onClick={onEdit}
          aria-label={`调整 ${cat.name} 预算`}
          className="flex w-full items-center justify-between gap-2 py-2 text-left font-normal transition-colors hover:bg-muted/40"
        >
          {inner}
        </button>
      ) : (
        <div className="flex w-full items-center justify-between gap-2 py-2">
          {inner}
        </div>
      )}
    </li>
  );
}
