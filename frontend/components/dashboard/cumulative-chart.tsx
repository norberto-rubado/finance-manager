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
  dayOfMonth: number; // 本月画到 dayOfMonth,非本月画到 totalDays
  isCurrentMonth: boolean;
  budget: string | null; // 总预算,用于画斜线
}

interface DayPoint {
  day: number;
  cumulative: number; // 累计支出
  budgetLine: number | null; // 预算斜线值 = budget * day / totalDays
}

export function CumulativeChart({
  year,
  month,
  totalDays,
  dayOfMonth,
  isCurrentMonth,
  budget,
}: Props) {
  const [points, setPoints] = useState<DayPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const start = new Date(year, month - 1, 1);
    const endDay = isCurrentMonth ? dayOfMonth : totalDays;
    const end = new Date(year, month - 1, endDay + 1); // [start, end)

    listTransactions({
      date_from: start.toISOString(),
      date_to: end.toISOString(),
      limit: 1000,
      is_mirror: false,
      kind: 'expense',
    })
      .then((res) => {
        // 按 day-of-month 桶累加
        const dailySpend = new Array(endDay + 1).fill(0); // index 1..endDay
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
            budgetLine: budgetNum === null ? null : (budgetNum * d) / totalDays,
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
          <Skeleton className="h-48 w-full md:h-64" />
        ) : (
          <div className="h-48 w-full md:h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={points}
                margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
              >
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
