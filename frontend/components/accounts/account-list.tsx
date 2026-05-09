'use client';

import { Pencil, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState } from '@/components/common/empty-state';
import type { AccountOut, AccountType } from '@/lib/api/types';

/**
 * **账户卡片网格。**
 *
 * **Backend schema 适配(Task 5 drift):**
 * - 字段 `type`(原 `account_type`)+ 5 值枚举(银行借记/信用、支付宝、微信、现金)
 * - `last4`(原 `last_four`)
 * - `archived`(原 `is_active` 反转)→ true 时卡片半透明 + "已停用" badge
 * - 不展示余额(后端无 `current_balance` 字段;余额需聚合交易,留给 summary 页)
 * - `currency` 非 CNY 时附带显示(MVP 大多数用户都是 CNY)
 */
const TYPE_LABEL: Record<AccountType, string> = {
  bank_debit: '银行借记卡',
  bank_credit: '银行信用卡',
  alipay: '支付宝',
  wechat: '微信',
  cash: '现金',
};

export function AccountList({
  items,
  onEdit,
  onDelete,
}: {
  items: AccountOut[];
  onEdit: (a: AccountOut) => void;
  onDelete: (a: AccountOut) => void;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="还没有账户"
        description='点上方"新建账户"添加第一个账户'
      />
    );
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((a) => (
        <li key={a.id}>
          <Card className={a.archived ? 'opacity-60' : ''}>
            <CardContent className="flex items-start justify-between gap-2 p-4">
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">{a.name}</span>
                  {a.archived && <Badge variant="outline">已停用</Badge>}
                </div>
                <div className="text-xs text-muted-foreground">
                  {TYPE_LABEL[a.type]}
                  {a.institution && ` · ${a.institution}`}
                  {a.last4 && ` · ****${a.last4}`}
                  {a.currency !== 'CNY' && ` · ${a.currency}`}
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onEdit(a)}
                  aria-label="编辑"
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onDelete(a)}
                  aria-label="删除"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
