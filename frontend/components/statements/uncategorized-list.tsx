'use client';

import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/common/empty-state';
import { BulkUpdateDialog } from '@/components/transactions/bulk-update-dialog';
import { fmtDateTime, fmtMoney } from '@/lib/utils/fmt';
import type { TransactionOut } from '@/lib/api/types';

/**
 * **未分类交易列表 —— Task 17。**
 *
 * 行为:
 * - 按 `merchant_normalized || merchant_raw || '(无商家)'` 分组
 * - 每行 / 整组 checkbox 选中
 * - 选中后底部"批量改类"按钮触发 BulkUpdateDialog(Task 13 复用)
 * - 跨商家选中时按钮 disabled —— `bulk-update-by-merchant` 单 pattern 语义
 *
 * **drift 适配:**
 * - `t.occurred_at` → `t.tx_time`
 * - `t.account_name` → 通过 accountMap 解(prop 注入)
 * - `bundle.uncategorized` → `bundle.unclassified_transactions`(在父页面已映射,这里收 items)
 */
export function UncategorizedList({
  items,
  accountMap,
  onChanged,
}: {
  items: TransactionOut[];
  accountMap: Map<number, string>;
  onChanged: () => void;
}) {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkOpen, setBulkOpen] = useState(false);

  // 分组:同 merchant 显示在一组卡片下
  const groups = useMemo(() => {
    const map = new Map<string, TransactionOut[]>();
    for (const t of items) {
      const key = t.merchant_normalized ?? t.merchant_raw ?? '(无商家)';
      const list = map.get(key);
      if (list) list.push(t);
      else map.set(key, [t]);
    }
    // 数量降序,便于把"高频未分类"放在最上面
    return Array.from(map.entries()).sort((a, b) => b[1].length - a[1].length);
  }, [items]);

  if (items.length === 0) {
    return (
      <EmptyState
        title="无未分类交易"
        description="本次导入的所有交易都已经命中分类规则"
      />
    );
  }

  const onToggleRow = (id: number) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const onToggleGroup = (groupItems: TransactionOut[], allSelected: boolean) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        for (const t of groupItems) next.delete(t.id);
      } else {
        for (const t of groupItems) next.add(t.id);
      }
      return next;
    });

  // 选中项跨商家时,batch dialog 默认值取空,按钮 disabled
  const selectedItems = items.filter((t) => selectedIds.has(t.id));
  const selectedMerchants = new Set(
    selectedItems
      .map((t) => t.merchant_normalized ?? t.merchant_raw ?? '')
      .filter(Boolean),
  );
  const sameMerchant = selectedMerchants.size === 1;
  const defaultMerchant = sameMerchant
    ? Array.from(selectedMerchants)[0]!
    : '';

  const onBulkSuccess = () => {
    setSelectedIds(new Set());
    onChanged();
  };

  return (
    <div className="space-y-3 pb-20">
      {groups.map(([merchant, list]) => {
        const allSelected = list.every((t) => selectedIds.has(t.id));
        const someSelected = !allSelected && list.some((t) => selectedIds.has(t.id));
        return (
          <Card key={merchant}>
            <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
              <div className="flex min-w-0 items-center gap-2">
                <Checkbox
                  aria-label={`选中分组 ${merchant}`}
                  checked={
                    allSelected ? true : someSelected ? 'indeterminate' : false
                  }
                  onCheckedChange={() => onToggleGroup(list, allSelected)}
                />
                <CardTitle className="truncate text-base">{merchant}</CardTitle>
                <Badge variant="secondary" className="font-normal">
                  {list.length}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <ul className="divide-y">
                {list.map((t) => {
                  const accountLabel =
                    accountMap.get(t.account_id) ?? `账户#${t.account_id}`;
                  const amountTone =
                    t.tx_kind === 'expense'
                      ? 'text-rose-500'
                      : t.tx_kind === 'income'
                        ? 'text-emerald-500'
                        : 'text-foreground';
                  return (
                    <li
                      key={t.id}
                      className="flex items-center gap-3 py-2 text-sm"
                    >
                      <Checkbox
                        aria-label={`选中交易 ${t.id}`}
                        checked={selectedIds.has(t.id)}
                        onCheckedChange={() => onToggleRow(t.id)}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                          <span className="tabular-nums text-muted-foreground">
                            {fmtDateTime(t.tx_time)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {accountLabel}
                          </span>
                        </div>
                        {t.description_raw && (
                          <div className="truncate text-xs text-muted-foreground">
                            {t.description_raw}
                          </div>
                        )}
                      </div>
                      <span
                        className={`shrink-0 font-semibold tabular-nums ${amountTone}`}
                      >
                        {fmtMoney(t.amount)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>
        );
      })}

      {/* 选中后底部固定 bar(同 transactions 页 BulkUpdateBar 的轻量本地版) */}
      {selectedItems.length > 0 && (
        <div className="fixed inset-x-0 bottom-14 z-30 flex items-center justify-between border-t bg-card/95 px-4 py-3 backdrop-blur md:bottom-0">
          <div className="flex items-center gap-2 text-sm">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedIds(new Set())}
            >
              取消选择
            </Button>
            <span>
              已选 <strong>{selectedItems.length}</strong> 条
              {!sameMerchant && (
                <span className="ml-2 text-muted-foreground">
                  (多商家;批量改类只支持单商家)
                </span>
              )}
            </span>
          </div>
          <Button
            size="sm"
            onClick={() => setBulkOpen(true)}
            disabled={!sameMerchant}
          >
            批量改类
          </Button>
        </div>
      )}

      <BulkUpdateDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        defaultMerchant={defaultMerchant}
        selectedCount={selectedItems.length}
        onSuccess={onBulkSuccess}
      />
    </div>
  );
}
