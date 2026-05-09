'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { toast } from 'sonner';

import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/common/empty-state';
import { ReviewTabs } from '@/components/statements/review-tabs';

import { getReviewBundle } from '@/lib/api/statements';
import type { ReviewBundle } from '@/lib/api/types';

/**
 * 账单导入复查页骨架。
 *
 * - URL: `/statements/{id}/review`
 * - useParams 拿 id → fetch ReviewBundle
 * - 渲染状态:loading skeleton / error EmptyState / 正常 ReviewTabs
 * - pendingSlot / uncategorizedSlot 暂用占位文本,Task 17 填实(去重对 card + 未分类批量改类)
 */
export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const importId = Number(params.id);
  const [bundle, setBundle] = useState<ReviewBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    getReviewBundle(importId)
      .then(setBundle)
      .catch((e: Error) => {
        setError(e.message);
        toast.error('加载复查包失败:' + e.message);
      });
  };

  useEffect(() => {
    if (Number.isNaN(importId)) {
      setError('无效的导入 ID');
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importId]);

  if (error) {
    return <EmptyState title="加载失败" description={error} />;
  }

  if (!bundle) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // Task 17 填充实际内容
  return (
    <ReviewTabs
      bundle={bundle}
      pendingSlot={
        <p className="text-sm text-muted-foreground">
          Task 17 实现去重对 card 列表
        </p>
      }
      uncategorizedSlot={
        <p className="text-sm text-muted-foreground">
          Task 17 实现未分类批量改类
        </p>
      }
    />
  );
}
