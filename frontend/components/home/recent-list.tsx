'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { listTransactions } from '@/lib/api/transactions';
import { listAccounts } from '@/lib/api/accounts';
import { listCategories } from '@/lib/api/categories';
import { fmtDateTime, fmtMoney } from '@/lib/utils/fmt';
import type { TransactionOut } from '@/lib/api/types';

export function RecentList() {
  const [items, setItems] = useState<TransactionOut[] | null>(null);
  const [accountMap, setAccountMap] = useState<Map<number, string>>(new Map());
  const [categoryMap, setCategoryMap] = useState<Map<number, string>>(new Map());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 并发抓 3 个端点;accounts/categories 失败仍可显示 items(用 fallback)
    Promise.all([
      listTransactions({ limit: 10, is_mirror: false }),
      listAccounts().catch(() => ({ items: [], total: 0 })),
      listCategories().catch(() => ({ items: [], total: 0 })),
    ])
      .then(([txRes, accRes, catRes]) => {
        setItems(txRes.items);
        setAccountMap(new Map(accRes.items.map((a) => [a.id, a.name])));
        setCategoryMap(new Map(catRes.items.map((c) => [c.id, c.name])));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base">最近 10 笔</CardTitle>
        <Button asChild variant="ghost" size="sm">
          <Link href="/transactions">查看全部</Link>
        </Button>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-destructive">加载失败:{error}</p>
        ) : items === null ? (
          <ul className="space-y-3">
            {Array.from({ length: 10 }).map((_, i) => (
              <li key={i}>
                <Skeleton className="h-10 w-full" />
              </li>
            ))}
          </ul>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无交易记录</p>
        ) : (
          <ul className="divide-y divide-border">
            {items.map((t) => (
              <RecentRow
                key={t.id}
                t={t}
                accountName={accountMap.get(t.account_id)}
                categoryName={t.category_id === null ? null : categoryMap.get(t.category_id) ?? null}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

interface RecentRowProps {
  t: TransactionOut;
  accountName: string | undefined;
  categoryName: string | null;
}

function RecentRow({ t, accountName, categoryName }: RecentRowProps) {
  const merchant = t.merchant_normalized ?? t.merchant_raw ?? '(无商家)';
  const accountLabel = accountName ?? `账户#${t.account_id}`;
  const amountNum = Number(t.amount);
  const isExpense = t.tx_kind === 'expense';
  const isIncome = t.tx_kind === 'income';
  const amountTone = isExpense
    ? 'text-rose-500'
    : isIncome
      ? 'text-emerald-500'
      : 'text-foreground';

  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{merchant}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{fmtDateTime(t.tx_time)}</span>
          <span aria-hidden>·</span>
          <span className="truncate">{accountLabel}</span>
          {categoryName ? (
            <Badge variant="secondary" className="font-normal">
              {categoryName}
            </Badge>
          ) : (
            <Badge variant="outline" className="font-normal">
              未分类
            </Badge>
          )}
        </div>
      </div>
      <div className={`text-sm font-semibold tabular-nums ${amountTone}`}>
        {fmtMoney(amountNum)}
      </div>
    </li>
  );
}
