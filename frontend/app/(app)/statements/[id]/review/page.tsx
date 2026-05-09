'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { toast } from 'sonner';

import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/common/empty-state';
import { ReviewTabs } from '@/components/statements/review-tabs';
import { PendingPairCard } from '@/components/statements/pending-pair-card';
import { UncategorizedList } from '@/components/statements/uncategorized-list';

import { listAccounts } from '@/lib/api/accounts';
import { getReviewBundle } from '@/lib/api/statements';
import { getTransaction } from '@/lib/api/transactions';
import type { ReviewBundle, TransactionOut } from '@/lib/api/types';

/**
 * 账单导入复查页 —— Task 16 骨架 + Task 17 内容。
 *
 * **drift(major)适配:**
 * 后端 `DedupPairOut` 只回 `primary_tx_id` / `mirror_tx_id`,**不嵌入** tx 对象,
 * 因此本页负责一次性 hydrate:
 *   1. fetch bundle(其中 unclassified_transactions 是完整 TransactionOut[])
 *   2. fetch accounts → accountMap
 *   3. 收集 pending_pairs 引用的所有 tx id,并发 getTransaction → txMap
 *   4. 把 (txMap, accountMap) 透传给 PendingPairCard;UncategorizedList 直接吃 bundle 的完整 tx
 *
 * `refresh()` 同时重抓 bundle + 重新 hydrate txMap(accountMap 一次性,改动罕见,不重抓)。
 */
export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const importId = Number(params.id);
  const [bundle, setBundle] = useState<ReviewBundle | null>(null);
  const [accountMap, setAccountMap] = useState<Map<number, string>>(new Map());
  const [txMap, setTxMap] = useState<Map<number, TransactionOut>>(new Map());
  const [error, setError] = useState<string | null>(null);

  // accounts 一次性加载 —— 跟 transactions 页同模式,改动罕见
  useEffect(() => {
    listAccounts()
      .then((r) => setAccountMap(new Map(r.items.map((a) => [a.id, a.name]))))
      .catch(() => {
        // 静默降级:accountMap 留空时 card 显示 "账户#id"
      });
  }, []);

  /**
   * Hydrate:取 bundle.pending_pairs 中所有 tx id,并发拉取详情,合并进 txMap。
   * 已经存在的 id 不重复 fetch(refresh 时只补差异)。
   * 单条 fetch 失败(404 / 网络错误)被吞掉 —— card 端会渲染 "(交易加载中…)" 占位。
   */
  const hydratePairTxs = async (b: ReviewBundle) => {
    const ids = new Set<number>();
    for (const p of b.pending_pairs) {
      ids.add(p.primary_tx_id);
      ids.add(p.mirror_tx_id);
    }
    if (ids.size === 0) {
      setTxMap(new Map());
      return;
    }
    const idList = Array.from(ids);
    const results = await Promise.allSettled(idList.map((id) => getTransaction(id)));
    const next = new Map<number, TransactionOut>();
    results.forEach((r, idx) => {
      if (r.status === 'fulfilled') {
        next.set(idList[idx]!, r.value);
      }
    });
    setTxMap(next);
  };

  const refresh = async () => {
    try {
      const b = await getReviewBundle(importId);
      setBundle(b);
      // 不 await accounts —— 已在初次 useEffect 触发。
      await hydratePairTxs(b);
    } catch (e) {
      const msg = (e as Error).message;
      setError(msg);
      toast.error('加载复查包失败:' + msg);
    }
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

  return (
    <ReviewTabs
      bundle={bundle}
      pendingSlot={
        bundle.pending_pairs.length === 0 ? (
          <EmptyState
            title="无待审核重复对"
            description="本次导入未触发去重规则"
          />
        ) : (
          <ul className="space-y-3">
            {bundle.pending_pairs.map((p) => (
              <li key={p.id}>
                <PendingPairCard
                  pair={p}
                  primaryTx={txMap.get(p.primary_tx_id)}
                  mirrorTx={txMap.get(p.mirror_tx_id)}
                  accountMap={accountMap}
                  onResolved={refresh}
                />
              </li>
            ))}
          </ul>
        )
      }
      uncategorizedSlot={
        <UncategorizedList
          items={bundle.unclassified_transactions}
          accountMap={accountMap}
          onChanged={refresh}
        />
      }
    />
  );
}
