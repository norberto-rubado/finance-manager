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

export function CategoryBudgetList({
  categories,
  periodYear,
  periodMonth,
  editable,
  onSaved,
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
                <>
                  {fmtMoney(spent, { bare: true })} / {fmtMoney(budget, { bare: true })}
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
