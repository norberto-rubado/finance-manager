'use client';

import { useEffect, useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

import { CategoryFormDialog } from '@/components/categories/category-form-dialog';
import { CategoryTree } from '@/components/categories/category-tree';
import { ConfirmDialog } from '@/components/common/confirm-dialog';

import { deleteCategory, listCategories } from '@/lib/api/categories';
import type { CategoryOut } from '@/lib/api/types';

/**
 * **分类管理页(Task 19)。**
 *
 * 5 大板块之一,支持:
 * - 2 级树形展示(顶级 → 子级)
 * - 新建/编辑(form dialog;编辑时禁用 kind 因后端不允许变更)
 * - 删除(destructive confirm dialog;后端被规则/交易引用或有子分类时返 409 → toast)
 *
 * 数据流:`refresh()` 每次操作后重拉列表(MVP 不做乐观更新,简单可靠)。
 * `parents` 由 `items` 派生(`parent_id === null` 的即顶级),传给 form 做父级下拉。
 */
export default function CategoriesPage() {
  const [items, setItems] = useState<CategoryOut[] | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CategoryOut | null>(null);
  const [pendingDelete, setPendingDelete] = useState<CategoryOut | null>(null);

  const refresh = () => {
    setItems(null);
    listCategories()
      .then((r) => setItems(r.items))
      .catch((e) => {
        toast.error((e as Error).message);
        setItems([]);
      });
  };

  useEffect(refresh, []);

  const parents = useMemo(
    () => (items ?? []).filter((c) => c.parent_id === null),
    [items],
  );

  const onCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const onEdit = (c: CategoryOut) => {
    setEditing(c);
    setFormOpen(true);
  };
  const onDelete = (c: CategoryOut) => setPendingDelete(c);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteCategory(pendingDelete.id);
      toast.success('已删除');
      refresh();
    } catch (e) {
      // 后端 409 = 分类被引用(子分类/规则/交易),提示用户
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">分类</h1>
        <Button onClick={onCreate}>
          <Plus className="mr-2 h-4 w-4" /> 新建分类
        </Button>
      </div>
      {items === null ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : (
        <CategoryTree items={items} onEdit={onEdit} onDelete={onDelete} />
      )}
      <CategoryFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editing}
        parents={parents}
        onSuccess={refresh}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title={`删除分类 "${pendingDelete?.name ?? ''}"?`}
        description="若有子分类或被规则/交易引用,删除会失败。"
        destructive
        confirmText="删除"
        onConfirm={confirmDelete}
      />
    </div>
  );
}
