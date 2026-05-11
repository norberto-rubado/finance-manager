import Link from 'next/link';
import { Shell } from '@/components/layout/shell';
import { Button } from '@/components/ui/button';
import { KpiCards } from '@/components/home/kpi-cards';
import { RecentList } from '@/components/home/recent-list';
import { SevenDayChart } from '@/components/home/seven-day-chart';

export default function HomePage() {
  return (
    <Shell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">本月概览</h1>
          <Button asChild variant="ghost" size="sm">
            <Link href="/dashboard">详查 →</Link>
          </Button>
        </div>
        <KpiCards />
        <div className="grid gap-4 lg:grid-cols-2">
          <RecentList />
          <SevenDayChart />
        </div>
      </div>
    </Shell>
  );
}
