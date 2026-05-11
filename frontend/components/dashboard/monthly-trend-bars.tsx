'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fmtMoney } from '@/lib/utils/fmt';
import type { SnapshotTrendPoint } from '@/lib/api/types';

interface Props {
  points: SnapshotTrendPoint[];
  highlightYear: number;
  highlightMonth: number;
}

interface BarPoint {
  label: string; // "5 月"
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
              <CartesianGrid
                strokeDasharray="3 3"
                className="stroke-border"
                vertical={false}
              />
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
                    fill={
                      d.isHighlight
                        ? 'hsl(var(--primary))'
                        : 'hsl(var(--muted-foreground) / 0.4)'
                    }
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
