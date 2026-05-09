'use client';

import { useEffect, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { listTransactions } from '@/lib/api/transactions';
import { fmtMoney } from '@/lib/utils/fmt';

interface DayPoint {
  date: string; // "MM-DD" 用作 x 轴显示
  iso: string; // "yyyy-MM-dd" 完整,Tooltip / debugging 用
  amount: number;
}

/** 取本地时区下 "yyyy-MM-dd"(避免 toISOString() 把日期推到前一天)。 */
function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** 生成最近 7 天的 0 值桶(包含今天),按时间升序。 */
function build7DayBuckets(today: Date): Map<string, DayPoint> {
  const buckets = new Map<string, DayPoint>();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const iso = ymdLocal(d);
    buckets.set(iso, { date: iso.slice(5), iso, amount: 0 });
  }
  return buckets;
}

export function SevenDayChart() {
  const [points, setPoints] = useState<DayPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const today = new Date();
    const sevenDaysAgo = new Date(today);
    sevenDaysAgo.setDate(today.getDate() - 6);
    sevenDaysAgo.setHours(0, 0, 0, 0);

    listTransactions({
      // 后端 date_from/date_to 是 datetime;ISO 串能直接 parse
      date_from: sevenDaysAgo.toISOString(),
      date_to: new Date(today.getTime() + 24 * 60 * 60 * 1000).toISOString(),
      limit: 500,
      is_mirror: false,
      kind: 'expense',
    })
      .then((res) => {
        const buckets = build7DayBuckets(today);
        for (const t of res.items) {
          // tx_time 是 ISO datetime;按本地时区取日期
          const day = ymdLocal(new Date(t.tx_time));
          const cur = buckets.get(day);
          if (!cur) continue; // 边界外丢弃
          // expense 在后端约定中通常 amount > 0(人话:"花了 30 块");
          // 防御性 Math.abs 兼容签名约定不一致的历史数据。
          cur.amount += Math.abs(Number(t.amount));
        }
        setPoints(Array.from(buckets.values()));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">近 7 天支出</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-destructive">加载失败:{error}</p>
        ) : points === null ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="date"
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
                  labelFormatter={(label: string) => label}
                  contentStyle={{
                    background: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '6px',
                    fontSize: '12px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="amount"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
