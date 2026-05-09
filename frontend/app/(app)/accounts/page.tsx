'use client';

import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

import { AccountFormDialog } from '@/components/accounts/account-form-dialog';
import { AccountList } from '@/components/accounts/account-list';
import { ConfirmDialog } from '@/components/common/confirm-dialog';

import { deleteAccount, listAccounts } from '@/lib/api/accounts';
import type { AccountOut } from '@/lib/api/types';

/**
 * **账户管理页(Task 18)。**
 *
 * 5 大板块之一,支持:
 * - 列表展示(卡片网格,响应式 1/2/3 列)
 * - 新建/编辑(form dialog)
 * - 删除(destructive confirm dialog;后端被引用时返 409 → toast)
 * - 停用/启用(走编辑 dialog 的 archived checkbox)
 *
 * 数据流:`refresh()` 每次操作后重拉列表(MVP 不做乐观更新,简单可靠)。
 */
export default function AccountsPage() {
  const [items, setItems] = useState<AccountOut[] | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<AccountOut | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AccountOut | null>(null);

  const refresh = () => {
    setItems(null);
    listAccounts()
      .then((r) => setItems(r.items))
      .catch((e) => {
        toast.error((e as Error).message);
        setItems([]);
      });
  };

  useEffect(refresh, []);

  const onCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const onEdit = (a: AccountOut) => {
    setEditing(a);
    setFormOpen(true);
  };
  const onDelete = (a: AccountOut) => setPendingDelete(a);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteAccount(pendingDelete.id);
      toast.success('已删除');
      refresh();
    } catch (e) {
      // 后端 409 = 账户被交易引用,提示用户改用停用
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">账户</h1>
        <Button onClick={onCreate}>
          <Plus className="mr-2 h-4 w-4" /> 新建账户
        </Button>
      </div>
      {items === null ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <AccountList items={items} onEdit={onEdit} onDelete={onDelete} />
      )}
      <AccountFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editing}
        onSuccess={refresh}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title={`删除账户 "${pendingDelete?.name ?? ''}"?`}
        description="如果该账户下还有交易,删除会失败。建议先停用。"
        destructive
        confirmText="删除"
        onConfirm={confirmDelete}
      />
    </div>
  );
}
