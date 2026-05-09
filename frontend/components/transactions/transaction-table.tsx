'use client';

import { Pencil } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { fmtDate, fmtMoney } from '@/lib/utils/fmt';
import type { TransactionOut } from '@/lib/api/types';

/**
 * 桌面交易表格(>= md)。
 *
 * **设计选择:**TransactionOut 上没有 `account_name` / `category_name`,
 * 所以由 page.tsx 把 accounts/categories list 转成 Map 后作 prop 传入,
 * 表格本身保持纯 presentational。
 */
export function TransactionTable({
  items,
  accountMap,
  categoryMap,
  selectedIds,
  onToggle,
  onToggleAll,
  onEdit,
}: {
  items: TransactionOut[];
  accountMap: Map<number, string>;
  categoryMap: Map<number, string>;
  selectedIds: Set<number>;
  onToggle: (id: number) => void;
  onToggleAll: (checked: boolean) => void;
  onEdit: (tx: TransactionOut) => void;
}) {
  const allChecked = items.length > 0 && items.every((t) => selectedIds.has(t.id));
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                aria-label="全选"
                checked={allChecked}
                onCheckedChange={(c) => onToggleAll(Boolean(c))}
              />
            </TableHead>
            <TableHead className="w-28">日期</TableHead>
            <TableHead>商家</TableHead>
            <TableHead className="w-32">分类</TableHead>
            <TableHead className="w-32">账户</TableHead>
            <TableHead className="w-32 text-right">金额</TableHead>
            <TableHead className="w-12"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
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
            const accountLabel = accountMap.get(t.account_id) ?? `账户#${t.account_id}`;
            const categoryName =
              t.category_id !== null && categoryMap.has(t.category_id)
                ? categoryMap.get(t.category_id)
                : null;
            return (
              <TableRow key={t.id} data-mirror={t.is_mirror ? 'true' : undefined}>
                <TableCell>
                  <Checkbox
                    aria-label={`选中 ${merchant}`}
                    checked={selectedIds.has(t.id)}
                    onCheckedChange={() => onToggle(t.id)}
                  />
                </TableCell>
                <TableCell className="tabular-nums text-sm">
                  {fmtDate(t.tx_time)}
                </TableCell>
                <TableCell className="max-w-xs">
                  <div className="truncate font-medium">{merchant}</div>
                  {t.merchant_raw && t.merchant_raw !== t.merchant_normalized && (
                    <div className="truncate text-xs text-muted-foreground">
                      {t.merchant_raw}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  {categoryName ? (
                    <Badge variant="secondary" className="font-normal">
                      {categoryName}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="font-normal">
                      未分类
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="truncate text-sm text-muted-foreground">
                  {accountLabel}
                </TableCell>
                <TableCell
                  className={`text-right font-semibold tabular-nums ${amountTone}`}
                >
                  {t.is_mirror && (
                    <span className="mr-1 text-xs font-normal text-muted-foreground">
                      (镜像)
                    </span>
                  )}
                  {fmtMoney(amountNum)}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="编辑"
                    onClick={() => onEdit(t)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
