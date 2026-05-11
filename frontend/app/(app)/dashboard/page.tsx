'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { EmptyState } from '@/components/common/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { MonthPicker, type MonthValue } from '@/components/dashboard/month-picker';
import { BudgetSummaryCard } from '@/components/dashboard/budget-summary-card';
import { CategoryBudgetList } from '@/components/dashboard/category-budget-list';
import { CumulativeChart } from '@/components/dashboard/cumulative-chart';
import { MonthPaceCard } from '@/components/dashboard/month-pace-card';
import { PendingActionsCard } from '@/components/dashboard/pending-actions-card';
import { CategoryDonut } from '@/components/dashboard/category-donut';
import { MonthlyTrendBars } from '@/components/dashboard/monthly-trend-bars';
import { getDashboardSnapshot } from '@/lib/api/dashboard';
import type { DashboardSnapshot } from '@/lib/api/types';

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <DashboardView />
    </Suspense>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-64 w-full" />
        ))}
      </div>
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function todayLocal(): { value: MonthValue; iso: string } {
  const d = new Date();
  const year = d.getFullYear();
  const month = d.getMonth() + 1;
  const day = String(d.getDate()).padStart(2, '0');
  return {
    value: { year, month },
    iso: `${year}-${String(month).padStart(2, '0')}-${day}`,
  };
}

function DashboardView() {
  const router = useRouter();
  const sp = useSearchParams();

  // URL → MonthValue;无 query 时用本地"今天",并立即 router.replace 同步
  const today = useMemo(() => todayLocal(), []);
  const urlYear = sp.get('year');
  const urlMonth = sp.get('month');

  useEffect(() => {
    if (urlYear === null || urlMonth === null) {
      const search = new URLSearchParams();
      search.set('year', String(today.value.year));
      search.set('month', String(today.value.month));
      router.replace(`/dashboard?${search.toString()}`);
    }
  }, [urlYear, urlMonth, today, router]);

  const month: MonthValue = useMemo(() => {
    if (urlYear !== null && urlMonth !== null) {
      return { year: Number(urlYear), month: Number(urlMonth) };
    }
    return today.value;
  }, [urlYear, urlMonth, today]);

  const [snap, setSnap] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // 拉 snapshot
  const fetchSnap = useCallback(() => {
    setError(null);
    setSnap(null);
    getDashboardSnapshot(month.year, month.month, today.iso)
      .then(setSnap)
      .catch((e: Error) => setError(e.message));
  }, [month.year, month.month, today.iso]);

  useEffect(() => {
    fetchSnap();
  }, [fetchSnap, refreshKey]);

  const onMonthChange = (v: MonthValue) => {
    const search = new URLSearchParams();
    search.set('year', String(v.year));
    search.set('month', String(v.month));
    router.push(`/dashboard?${search.toString()}`);
  };

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <EmptyState
          title="加载失败"
          description={error}
          action={<Button onClick={() => setRefreshKey((k) => k + 1)}>重试</Button>}
        />
      </div>
    );
  }

  if (snap === null) {
    return <DashboardSkeleton />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <MonthPicker value={month} onChange={onMonthChange} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <BudgetSummaryCard total={snap.total} pace={snap.pace} />
        {snap.period.is_current_month && (
          <MonthPaceCard period={snap.period} total={snap.total} pace={snap.pace} />
        )}
      </div>

      <CumulativeChart
        year={snap.period.year}
        month={snap.period.month}
        totalDays={snap.period.total_days}
        dayOfMonth={snap.period.day_of_month}
        isCurrentMonth={snap.period.is_current_month}
        budget={snap.total.budget}
      />

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
        {snap.period.is_current_month && <PendingActionsCard pending={snap.pending} />}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <CategoryDonut categories={snap.categories} />
        <MonthlyTrendBars
          points={snap.monthly_trend}
          highlightYear={snap.period.year}
          highlightMonth={snap.period.month}
        />
      </div>
    </div>
  );
}
