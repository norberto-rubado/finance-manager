'use client';

import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

import { RuleFormDialog } from '@/components/rules/rule-form-dialog';
import { RuleList } from '@/components/rules/rule-list';
import { ConfirmDialog } from '@/components/common/confirm-dialog';

import { listCategories } from '@/lib/api/categories';
import { deleteRule, listRules } from '@/lib/api/rules';
import type { CategoryOut, MerchantRuleOut } from '@/lib/api/types';

/**
 * **商家规则管理页(Task 20)。**
 *
 * 5 大板块之一,支持:
 * - 列表展示(按 priority 升序;数字越小越先匹配)
 * - 新建/编辑(form dialog,含 marker rule 切换)
 * - 删除(destructive confirm dialog)
 *
 * **marker rule 特殊设计(spec § slice A Rec #5):**
 * 与普通规则的区别仅在 `category_id === null`:命中时只累加 `hit_count`,
 * 不改交易分类。slice A seed 已注入 6 条 marker(priority=20),用于打标
 * 跨境交易、特殊渠道等"识别但暂不归类"场景。
 *
 * 数据流:`refresh()` 并发拉取 rules + categories(分类用于列表显示分类名),
 * 每次操作后重拉(MVP 不做乐观更新,简单可靠)。
 */
export default function RulesPage() {
  const [items, setItems] = useState<MerchantRuleOut[] | null>(null);
  const [cats, setCats] = useState<CategoryOut[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<MerchantRuleOut | null>(null);
  const [pendingDelete, setPendingDelete] = useState<MerchantRuleOut | null>(
    null,
  );

  const refresh = () => {
    setItems(null);
    Promise.all([listRules(), listCategories()])
      .then(([r, c]) => {
        setItems(r.items.sort((a, b) => a.priority - b.priority));
        setCats(c.items);
      })
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
  const onEdit = (r: MerchantRuleOut) => {
    setEditing(r);
    setFormOpen(true);
  };
  const onDelete = (r: MerchantRuleOut) => setPendingDelete(r);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteRule(pendingDelete.id);
      toast.success('已删除');
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">商家规则</h1>
        <Button onClick={onCreate}>
          <Plus className="mr-2 h-4 w-4" /> 新建规则
        </Button>
      </div>
      {items === null ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <RuleList
          items={items}
          categories={cats}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      )}
      <RuleFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editing}
        onSuccess={refresh}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title={`删除规则 "${pendingDelete?.pattern ?? ''}"?`}
        description="此操作不可逆。"
        destructive
        confirmText="删除"
        onConfirm={confirmDelete}
      />
    </div>
  );
}
