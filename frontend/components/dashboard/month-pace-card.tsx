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
export function paceDescriptor(delta: number | null): { text: string; tone: string } {
  if (delta === null) return { text: '—', tone: 'text-muted-foreground' };
  if (delta > 10) return { text: `提前 ${delta.toFixed(0)}%`, tone: 'text-rose-500' };
  if (delta < -10)
    return { text: `落后 ${Math.abs(delta).toFixed(0)}%`, tone: 'text-emerald-500' };
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
    const pct = ((thisSpent - prevSpent) / prevSpent) * 100;
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
            <dd className={`mt-1 text-lg font-semibold ${desc.tone}`}>{desc.text}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">vs 上月</dt>
            <dd className={`mt-1 text-lg font-semibold ${vsPrev.tone}`}>{vsPrev.text}</dd>
          </div>
        </dl>
        <div className="mt-3 text-xs text-muted-foreground">
          上月支出 {fmtMoney(prevSpent)}
        </div>
      </CardContent>
    </Card>
  );
}
