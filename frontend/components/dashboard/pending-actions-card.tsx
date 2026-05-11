'use client';

import Link from 'next/link';
import { AlertTriangle, Inbox, Search } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { SnapshotPending } from '@/lib/api/types';

interface Props {
  pending: SnapshotPending;
}

interface ChipProps {
  href: string;
  icon: React.ReactNode;
  label: string;
  count: number;
  tone: 'warning' | 'info' | 'neutral';
}

const TONE_CLASS: Record<ChipProps['tone'], string> = {
  warning: 'border-rose-500/40 bg-rose-500/10 text-rose-200',
  info: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
  neutral: 'border-border bg-muted text-muted-foreground',
};

function Chip({ href, icon, label, count, tone }: ChipProps) {
  return (
    <Link
      href={href}
      className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2 transition-colors hover:opacity-90 ${TONE_CLASS[tone]}`}
    >
      <span className="flex items-center gap-2 text-sm">
        {icon}
        {label}
      </span>
      <span className="text-base font-semibold tabular-nums">{count}</span>
    </Link>
  );
}

export function PendingActionsCard({ pending }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">待处理</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Chip
          href="#category-budget-list"
          icon={<AlertTriangle className="h-4 w-4" />}
          label="超支类别"
          count={pending.overspending_count}
          tone={pending.overspending_count > 0 ? 'warning' : 'neutral'}
        />
        <Chip
          href="/transactions?category_id=null"
          icon={<Inbox className="h-4 w-4" />}
          label="未分类交易"
          count={pending.uncategorized_count}
          tone={pending.uncategorized_count > 0 ? 'info' : 'neutral'}
        />
        <Chip
          href="/statements"
          icon={<Search className="h-4 w-4" />}
          label="待审核去重"
          count={pending.dedup_pending_count}
          tone={pending.dedup_pending_count > 0 ? 'info' : 'neutral'}
        />
      </CardContent>
    </Card>
  );
}
