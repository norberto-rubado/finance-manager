'use client';

import { useState } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { fmtDateTime, fmtMoney, fmtPercent } from '@/lib/utils/fmt';
import { confirmPair, rejectPair } from '@/lib/api/dedup';
import type {
  DedupMatchKind,
  DedupPairOut,
  TransactionOut,
} from '@/lib/api/types';

/**
 * **待审核去重对 card —— Task 17。**
 *
 * **drift(major)适配:** 后端 `DedupPairOut` 只回 ID,不含嵌入的 source/mirror tx 对象。
 * 父页面(review/page.tsx)负责一次性 hydrate `txMap`,通过 `primaryTx` / `mirrorTx`
 * prop 注入;card 本身保持 presentational。
 *
 * **字段映射:**
 * - plan `pair.signal` → backend `pair.match_kind`(三值:strong/bridge/conversation)
 * - plan `pair.notes` → backend `pair.reasoning: dict | null`(MVP 走 JSON.stringify)
 * - plan `pair.pair_id` → backend `pair.id`
 * - tx 字段:`tx.occurred_at` → `tx.tx_time`;`tx.account_name` → 由 accountMap 解
 */

const MATCH_KIND_LABEL: Record<DedupMatchKind, string> = {
  strong: '强匹配',
  bridge: '桥接匹配',
  conversation: '会话匹配',
};

const MATCH_KIND_VARIANT: Record<
  DedupMatchKind,
  'default' | 'secondary' | 'outline'
> = {
  strong: 'default',
  bridge: 'secondary',
  conversation: 'outline',
};

/**
 * 单条交易展示块 —— card 内并列展示主/镜像两条。
 * tx undefined 时给"加载中"占位(初次渲染或 hydration 尚未完成)。
 */
function TxBlock({
  label,
  tx,
  accountMap,
}: {
  label: string;
  tx: TransactionOut | undefined;
  accountMap: Map<number, string>;
}) {
  if (!tx) {
    return (
      <div className="space-y-1.5 rounded-md border bg-muted/30 p-3">
        <div className="text-xs font-medium text-muted-foreground">{label}</div>
        <div className="text-sm text-muted-foreground">(交易加载中…)</div>
      </div>
    );
  }
  const merchant = tx.merchant_normalized ?? tx.merchant_raw ?? '(无商家)';
  const accountLabel = accountMap.get(tx.account_id) ?? `账户#${tx.account_id}`;
  const amountTone =
    tx.tx_kind === 'expense'
      ? 'text-rose-500'
      : tx.tx_kind === 'income'
        ? 'text-emerald-500'
        : 'text-foreground';
  return (
    <div className="space-y-1.5 rounded-md border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {tx.is_mirror && (
          <Badge variant="outline" className="font-normal">
            镜像
          </Badge>
        )}
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium">{merchant}</span>
        <span className={`shrink-0 text-sm font-semibold tabular-nums ${amountTone}`}>
          {fmtMoney(tx.amount)}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
        <span className="tabular-nums">{fmtDateTime(tx.tx_time)}</span>
        <span aria-hidden>·</span>
        <span className="truncate">{accountLabel}</span>
        <span aria-hidden>·</span>
        <span className="uppercase">{tx.source}</span>
      </div>
      {tx.description_raw && (
        <div className="truncate text-xs text-muted-foreground">
          {tx.description_raw}
        </div>
      )}
    </div>
  );
}

export function PendingPairCard({
  pair,
  primaryTx,
  mirrorTx,
  accountMap,
  onResolved,
}: {
  pair: DedupPairOut;
  primaryTx: TransactionOut | undefined;
  mirrorTx: TransactionOut | undefined;
  accountMap: Map<number, string>;
  onResolved: (id: number) => void;
}) {
  const [busy, setBusy] = useState<'confirm' | 'reject' | null>(null);

  const onConfirm = async () => {
    setBusy('confirm');
    try {
      await confirmPair(pair.id);
      toast.success('已确认为同一笔');
      onResolved(pair.id);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onReject = async () => {
    setBusy('reject');
    try {
      await rejectPair(pair.id);
      toast.success('已拒绝(保留两条)');
      onResolved(pair.id);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  // reasoning 是 dict | null;MVP 直接 JSON dump。复杂渲染留给后续 polish。
  const reasoningText =
    pair.reasoning && Object.keys(pair.reasoning).length > 0
      ? JSON.stringify(pair.reasoning)
      : null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={MATCH_KIND_VARIANT[pair.match_kind]}>
            {MATCH_KIND_LABEL[pair.match_kind]}
          </Badge>
          <Badge variant="outline">置信度 {fmtPercent(pair.confidence)}</Badge>
          <span className="text-xs text-muted-foreground">配对 #{pair.id}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <TxBlock label="主交易" tx={primaryTx} accountMap={accountMap} />
          <TxBlock label="镜像交易" tx={mirrorTx} accountMap={accountMap} />
        </div>
        {reasoningText && (
          <div className="rounded-md border bg-muted/20 p-2 text-xs text-muted-foreground">
            <span className="font-medium">证据:</span>{' '}
            <span className="break-all">{reasoningText}</span>
          </div>
        )}
        <Separator />
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onReject}
            disabled={busy !== null}
          >
            {busy === 'reject' ? '处理中…' : '拒绝'}
          </Button>
          <Button size="sm" onClick={onConfirm} disabled={busy !== null}>
            {busy === 'confirm' ? '处理中…' : '确认'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
