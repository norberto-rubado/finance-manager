'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { copyBudgetsFrom } from '@/lib/api/budgets';
import { ApiClientError } from '@/lib/api/types';

interface Props {
  year: number;
  month: number;
  onSuccess: () => void;
}

/** 从上月复制预算。目标月已有数据时,后端返 409 → toast 提示先清空。 */
export function CopyFromPrevButton({ year, month, onSuccess }: Props) {
  const [busy, setBusy] = useState(false);

  function prevMonth(y: number, m: number): { year: number; month: number } {
    if (m === 1) return { year: y - 1, month: 12 };
    return { year: y, month: m - 1 };
  }

  async function onClick() {
    const prev = prevMonth(year, month);
    setBusy(true);
    try {
      const res = await copyBudgetsFrom({
        from_year: prev.year,
        from_month: prev.month,
        to_year: year,
        to_month: month,
      });
      if (res.length === 0) {
        toast.info('上月没有任何预算,不能复制');
      } else {
        toast.success(`已从 ${prev.year} 年 ${prev.month} 月复制 ${res.length} 条预算`);
        onSuccess();
      }
    } catch (e) {
      if (e instanceof ApiClientError && e.status === 409) {
        toast.error('当月已有预算,清空后再复制');
      } else {
        toast.error('复制失败:' + (e instanceof Error ? e.message : String(e)));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={busy}>
      <Copy className="mr-2 h-4 w-4" />
      {busy ? '复制中…' : '复制上月'}
    </Button>
  );
}
