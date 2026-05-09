'use client';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { fmtDateTime } from '@/lib/utils/fmt';
import type { ReviewBundle } from '@/lib/api/types';

/**
 * 复查页头部 + Tabs 容器。pendingSlot / uncategorizedSlot 由父页面注入(Task 17 填实)。
 *
 * **drift 适配:**
 * - `bundle.import` → `bundle.statement`(后端字段名)
 * - `bundle.uncategorized` → `bundle.unclassified_transactions`(后端字段名)
 * - `bundle.progress` 后端**不存在** —— 移除 ProgressBar,改用待审核计数文本
 *   (无虚假百分比;真正全量进度需要后端额外端点,超出 slice D 范围)
 * - 字段名映射:
 *   `imp.uploaded_at` → `imp.imported_at`
 *   `imp.parsed_count` → `imp.raw_row_count`
 *   `imp.duplicate_skipped_count` → `imp.deduped_count`
 */
export function ReviewTabs({
  bundle,
  pendingSlot,
  uncategorizedSlot,
}: {
  bundle: ReviewBundle;
  pendingSlot: React.ReactNode;
  uncategorizedSlot: React.ReactNode;
}) {
  const { statement: imp, pending_pairs, unclassified_transactions } = bundle;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            导入复查 #{imp.id}
            <Badge variant="outline">{imp.source_type}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
            <span>{imp.filename}</span>
            <span>{fmtDateTime(imp.imported_at)}</span>
            <span>解析 {imp.raw_row_count} 条</span>
            <span>入库 {imp.imported_count} 条</span>
            <span>重复 {imp.deduped_count} 条</span>
            <span>已分类 {imp.classified_count} 条</span>
            <span>待审核 {pending_pairs.length} 对</span>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="pending" className="w-full">
        <TabsList className="grid w-full grid-cols-2 sm:w-auto sm:inline-grid sm:grid-cols-2">
          <TabsTrigger value="pending">
            待审核去重
            {pending_pairs.length > 0 && (
              <Badge className="ml-2">{pending_pairs.length}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="uncategorized">
            未分类
            {unclassified_transactions.length > 0 && (
              <Badge className="ml-2">{unclassified_transactions.length}</Badge>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="pending" className="mt-4">
          {pendingSlot}
        </TabsContent>
        <TabsContent value="uncategorized" className="mt-4">
          {uncategorizedSlot}
        </TabsContent>
      </Tabs>
    </div>
  );
}
