'use client';

import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { TransactionOut } from '@/lib/api/types';

/**
 * **批量操作底部固定 bar。**
 *
 * 出现条件:`selectedItems.length > 0`。
 * - 桌面:贴底(bottom-0)
 * - 手机:在 tabbar 上方(bottom-14,留出 tabbar 高度)
 *
 * 多商家选中时"批量改类"按钮 disabled —— 跨商家批改超出 backend
 * `bulk-update-by-merchant` 单 pattern 的语义,Task 14 单条编辑覆盖此场景。
 */
export function BulkUpdateBar({
  selectedItems,
  onClear,
  onBulkUpdate,
}: {
  selectedItems: TransactionOut[];
  onClear: () => void;
  onBulkUpdate: (defaultMerchant: string) => void;
}) {
  if (selectedItems.length === 0) return null;

  // 取第一个选中项的商家做默认值;多商家时禁用按钮(由 dialog/Task 14 单条覆盖)
  const merchants = new Set(
    selectedItems
      .map((t) => t.merchant_normalized ?? t.merchant_raw ?? '')
      .filter(Boolean),
  );
  const defaultMerchant = merchants.size === 1 ? Array.from(merchants)[0]! : '';
  const sameMerchant = merchants.size === 1;

  return (
    <div className="fixed inset-x-0 bottom-14 z-30 flex items-center justify-between border-t bg-card/95 px-4 py-3 backdrop-blur md:bottom-0">
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={onClear}
          aria-label="取消选择"
        >
          <X className="h-4 w-4" />
        </Button>
        <span className="text-sm">
          已选 <strong>{selectedItems.length}</strong> 条
          {!sameMerchant && (
            <span className="ml-2 text-muted-foreground">
              (多商家;批量改类只支持单商家)
            </span>
          )}
        </span>
      </div>
      <Button
        onClick={() => onBulkUpdate(defaultMerchant)}
        disabled={!sameMerchant}
      >
        批量改类
      </Button>
    </div>
  );
}
