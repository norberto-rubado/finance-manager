'use client';

import { Pencil } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { fmtDate, fmtMoney } from '@/lib/utils/fmt';
import type { TransactionOut } from '@/lib/api/types';

/**
 * 手机交易卡片视图(< md)。
 *
 * **设计选择(同 TransactionTable):**TransactionOut 上没有 `account_name` /
 * `category_name`,所以由 page.tsx 把 accounts / categories list 转成 Map 后作 prop
 * 传入,卡片本身保持纯 presentational。
 */
export function TransactionCards({
  items,
  accountMap,
  categoryMap,
  selectedIds,
  onToggle,
  onEdit,
}: {
  items: TransactionOut[];
  accountMap: Map<number, string>;
  categoryMap: Map<number, string>;
  selectedIds: Set<number>;
  onToggle: (id: number) => void;
  onEdit: (tx: TransactionOut) => void;
}) {
  return (
    <ul className="space-y-2">
      {items.map((t) => {
        const amountNum = Number(t.amount);
        const isExpense = t.tx_kind === 'expense';
        const isIncome = t.tx_kind === 'income';
        const amountTone = isExpense
          ? 'text-rose-500'
          : isIncome
            ? 'text-emerald-500'
            : 'text-foreground';
        const merchant = t.merchant_normalized ?? t.merchant_raw ?? '(无商家)';
        const accountLabel =
          accountMap.get(t.account_id) ?? `账户#${t.account_id}`;
        const categoryName =
          t.category_id !== null && categoryMap.has(t.category_id)
            ? categoryMap.get(t.category_id)
            : null;
        return (
          <li key={t.id}>
            <Card
              className="flex items-start gap-3 p-3"
              data-mirror={t.is_mirror ? 'true' : undefined}
            >
              <Checkbox
                aria-label={`选中 ${merchant}`}
                checked={selectedIds.has(t.id)}
                onCheckedChange={() => onToggle(t.id)}
                className="mt-1"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">
                    {merchant}
                  </span>
                  <span
                    className={`shrink-0 text-sm font-semibold tabular-nums ${amountTone}`}
                  >
                    {fmtMoney(amountNum)}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="tabular-nums">{fmtDate(t.tx_time)}</span>
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
                  {t.is_mirror && (
                    <Badge variant="outline" className="font-normal">
                      镜像
                    </Badge>
                  )}
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label="编辑"
                onClick={() => onEdit(t)}
              >
                <Pencil className="h-4 w-4" />
              </Button>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
