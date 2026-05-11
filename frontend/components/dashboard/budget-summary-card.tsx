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
  if (ratio > 1) return 'hsl(0 84% 60%)'; // rose-500
  if (ratio > 0.8) return 'hsl(38 92% 50%)'; // amber-500
  return 'hsl(160 84% 39%)'; // emerald-500
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
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke="hsl(var(--muted))"
            strokeWidth="12"
          />
          <circle
            cx="80"
            cy="80"
            r={radius}
            fill="none"
            stroke={ringColor(ratio)}
            strokeWidth="12"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            transform="rotate(-90 80 80)"
          />
          <text
            x="80"
            y="76"
            textAnchor="middle"
            className="fill-foreground"
            style={{ font: '600 22px var(--font-inter)' }}
          >
            {Math.round(ratio * 100)}%
          </text>
          <text
            x="80"
            y="98"
            textAnchor="middle"
            className="fill-muted-foreground"
            style={{ font: '12px var(--font-inter)' }}
          >
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
