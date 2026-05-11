'use client';

import { useMemo } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fmtMoney } from '@/lib/utils/fmt';
import type { SnapshotCategory } from '@/lib/api/types';

interface Props {
  categories: SnapshotCategory[];
}

const PALETTE = [
  'hsl(160 84% 39%)', // emerald-600
  'hsl(217 91% 60%)', // blue-500
  'hsl(38 92% 50%)', // amber-500
  'hsl(280 65% 60%)', // purple-500
  'hsl(0 84% 60%)', // rose-500
  'hsl(195 53% 50%)', // sky-500 — "其他" 槽
];

interface Slice {
  name: string;
  value: number;
  color: string;
}

export function CategoryDonut({ categories }: Props) {
  const data = useMemo<Slice[]>(() => {
    const withSpent = categories
      .filter((c) => Number(c.spent) > 0)
      .map((c) => ({ name: c.name, value: Number(c.spent) }))
      .sort((a, b) => b.value - a.value);

    if (withSpent.length === 0) return [];

    const top5 = withSpent.slice(0, 5);
    const rest = withSpent.slice(5);
    const restSum = rest.reduce((s, x) => s + x.value, 0);

    const slices: Slice[] = top5.map((x, i) => ({
      name: x.name,
      value: x.value,
      color: PALETTE[i],
    }));
    if (restSum > 0) {
      slices.push({ name: '其他', value: restSum, color: PALETTE[5] });
    }
    return slices;
  }, [categories]);

  const total = data.reduce((s, x) => s + x.value, 0);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">分类占比</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            本月还没有支出
          </p>
        ) : (
          <>
            <div className="relative h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    stroke="hsl(var(--background))"
                    strokeWidth={2}
                  >
                    {data.map((s) => (
                      <Cell key={s.name} fill={s.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number) => fmtMoney(value)}
                    contentStyle={{
                      background: 'hsl(var(--popover))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '6px',
                      fontSize: '12px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-xs text-muted-foreground">本月总额</span>
                <span className="text-lg font-semibold tabular-nums">
                  {fmtMoney(total)}
                </span>
              </div>
            </div>
            <ul className="mt-4 grid grid-cols-2 gap-1 text-xs">
              {data.map((s) => (
                <li key={s.name} className="flex items-center gap-2">
                  <span
                    className="h-3 w-3 flex-shrink-0 rounded-sm"
                    style={{ background: s.color }}
                  />
                  <span className="truncate">{s.name}</span>
                  <span className="ml-auto tabular-nums text-muted-foreground">
                    {((s.value / total) * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
