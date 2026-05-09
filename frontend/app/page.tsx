import { Shell } from '@/components/layout/shell';
import { KpiCards } from '@/components/home/kpi-cards';
import { RecentList } from '@/components/home/recent-list';
import { SevenDayChart } from '@/components/home/seven-day-chart';

export default function HomePage() {
  return (
    <Shell>
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">本月概览</h1>
        <KpiCards />
        <div className="grid gap-4 lg:grid-cols-2">
          <RecentList />
          <SevenDayChart />
        </div>
      </div>
    </Shell>
  );
}
