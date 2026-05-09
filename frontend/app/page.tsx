import { Shell } from '@/components/layout/shell';
import { KpiCards } from '@/components/home/kpi-cards';

export default function HomePage() {
  return (
    <Shell>
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">本月概览</h1>
        <KpiCards />
        {/* Task 10:RecentList + SevenDayChart */}
      </div>
    </Shell>
  );
}
