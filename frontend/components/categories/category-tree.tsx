'use client';

import { Pencil, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState } from '@/components/common/empty-state';
import type { CategoryKind, CategoryOut } from '@/lib/api/types';

/**
 * **分类 2 级树。**
 *
 * **Backend schema 适配(Task 5 drift):**
 * - `kind` 枚举 3 值:`expense` / `income` / `neutral`(plan 原稿 `transfer` 已弃用)
 * - 新增 `color` 字段 → 行首显示色块,辅助快速识别(无 color 时不展示)
 *
 * **结构假设:**仅渲染 2 级(顶级 + 直接子级)。后端可能允许更深嵌套,但 MVP UI
 * 不展示;若出现 grandchild 类(parent_id 指向非顶级),它不会被任何 top.id 匹配,
 * 因此被静默忽略 —— 这符合 spec § 数据模型「2 级分类」的约束。
 *
 * **排序:**先按 `sort_order` 升序,再按 `id` 升序(同 sort_order 时 id 小的在前)。
 */
const KIND_LABEL: Record<CategoryKind, string> = {
  expense: '支出',
  income: '收入',
  neutral: '中性',
};

export function CategoryTree({
  items,
  onEdit,
  onDelete,
}: {
  items: CategoryOut[];
  onEdit: (c: CategoryOut) => void;
  onDelete: (c: CategoryOut) => void;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="还没有分类"
        description='点上方"新建分类"添加第一个'
      />
    );
  }

  // 顶级:parent_id === null
  const tops = items
    .filter((c) => c.parent_id === null)
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  const childrenOf = (pid: number) =>
    items
      .filter((c) => c.parent_id === pid)
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);

  return (
    <ul className="space-y-3">
      {tops.map((top) => {
        const children = childrenOf(top.id);
        return (
          <li key={top.id}>
            <Card>
              <CardContent className="space-y-2 p-3">
                <Row
                  item={top}
                  onEdit={onEdit}
                  onDelete={onDelete}
                  indent={false}
                />
                {children.length > 0 && (
                  <ul className="space-y-1 border-l pl-4">
                    {children.map((child) => (
                      <li key={child.id}>
                        <Row
                          item={child}
                          onEdit={onEdit}
                          onDelete={onDelete}
                          indent
                        />
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

function Row({
  item,
  onEdit,
  onDelete,
  indent,
}: {
  item: CategoryOut;
  onEdit: (c: CategoryOut) => void;
  onDelete: (c: CategoryOut) => void;
  indent: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between gap-2 ${
        indent ? 'text-sm' : 'font-medium'
      }`}
    >
      <div className="flex min-w-0 items-center gap-2">
        {item.color && (
          <span
            aria-hidden
            className="inline-block h-3 w-3 shrink-0 rounded-full border"
            style={{ backgroundColor: item.color }}
          />
        )}
        {item.icon && <span aria-hidden>{item.icon}</span>}
        <span className="truncate">{item.name}</span>
        <Badge variant="outline">{KIND_LABEL[item.kind]}</Badge>
      </div>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onEdit(item)}
          aria-label="编辑"
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onDelete(item)}
          aria-label="删除"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
