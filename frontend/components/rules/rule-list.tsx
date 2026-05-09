'use client';

import { Pencil, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState } from '@/components/common/empty-state';
import type {
  CategoryOut,
  MerchantRuleOut,
  RuleMatchKind,
} from '@/lib/api/types';

/**
 * **商家规则列表(Task 20)。**
 *
 * **Backend schema 适配(plan 原稿 drift):**
 * - `pattern_type` → `match_kind`(types.ts 已重命名)
 * - 4 值标签映射(plan 3 值 + 新增 `fuzzy`)
 * - 移除 `notes` 显示 —— 后端无该字段
 *
 * marker rule(`category_id === null`)用 secondary badge "仅标记" 区分,
 * 隐藏 "→ 分类" 行,避免误导。
 */
const PATTERN_LABEL: Record<RuleMatchKind, string> = {
  exact: '精确',
  contains: '包含',
  regex: '正则',
  fuzzy: '模糊',
};

export function RuleList({
  items,
  categories,
  onEdit,
  onDelete,
}: {
  items: MerchantRuleOut[];
  categories: CategoryOut[];
  onEdit: (r: MerchantRuleOut) => void;
  onDelete: (r: MerchantRuleOut) => void;
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="还没有规则"
        description='点上方"新建规则"添加第一条'
      />
    );
  }

  const catName = (id: number | null) =>
    id === null ? null : categories.find((c) => c.id === id)?.name ?? `#${id}`;

  return (
    <ul className="space-y-2">
      {items.map((r) => {
        const isMarker = r.category_id === null;
        return (
          <li key={r.id}>
            <Card>
              <CardContent className="flex items-center justify-between gap-3 p-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">
                      {PATTERN_LABEL[r.match_kind]}
                    </Badge>
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {r.pattern}
                    </code>
                    {isMarker ? (
                      <Badge variant="secondary">仅标记</Badge>
                    ) : (
                      <>
                        <span className="text-xs text-muted-foreground">→</span>
                        <Badge>{catName(r.category_id)}</Badge>
                      </>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                    <span>优先级 {r.priority}</span>
                    <span>命中 {r.hit_count} 次</span>
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => onEdit(r)}
                    aria-label="编辑"
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => onDelete(r)}
                    aria-label="删除"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
