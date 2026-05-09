'use client';

import { useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Scale, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { apiFetch } from '@/lib/api/client';
import { getSummary } from '@/lib/api/summary';
import { fmtMoney } from '@/lib/utils/fmt';
import type { PendingPairListOut, SummaryOut, SummaryPeriod } from '@/lib/api/types';

const PERIOD_LABEL: Record<SummaryPeriod, string> = {
  day: '今日',
  week: '本周',
  month: '本月',
  year: '今年',
};

export function KpiCards() {
  const [data, setData] = useState<SummaryOut | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSummary({ period: 'month' })
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    // 单独抓 dedup pending — 失败不阻塞 KPI 卡片
    apiFetch<PendingPairListOut>('/dedup/pending', { query: { limit: 1 } })
      .then((res) => setPendingCount(res.total))
      .catch(() => setPendingCount(null));
  }, []);

  if (error) {
    return <p className="text-sm text-destructive">加载概览失败:{error}</p>;
  }

  if (!data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    );
  }

  const netNum = Number(data.total_income) - Number(data.total_expense);
  const periodLabel = PERIOD_LABEL[data.period];
  const pendingDisplay = pendingCount === null ? '—' : String(pendingCount);
  const pendingTone =
    pendingCount !== null && pendingCount > 0 ? 'text-amber-500' : 'text-muted-foreground';

  const items = [
    {
      label: '本月支出',
      value: fmtMoney(data.total_expense),
      icon: ArrowDownRight,
      tone: 'text-rose-500',
    },
    {
      label: '本月收入',
      value: fmtMoney(data.total_income),
      icon: ArrowUpRight,
      tone: 'text-emerald-500',
    },
    {
      label: '净额',
      value: fmtMoney(netNum),
      icon: Scale,
      tone: 'text-foreground',
    },
    {
      label: '待审核',
      value: pendingDisplay,
      icon: AlertCircle,
      tone: pendingTone,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((it) => {
        const Icon = it.icon;
        return (
          <Card key={it.label}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{it.label}</CardTitle>
              <Icon className={`h-4 w-4 ${it.tone}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-semibold">{it.value}</div>
              <div className="text-xs text-muted-foreground mt-1">{periodLabel}</div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
