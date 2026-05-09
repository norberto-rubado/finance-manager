'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Eye } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { listStatements } from '@/lib/api/statements';
import { fmtDate, fmtDateTime } from '@/lib/utils/fmt';
import { EmptyState } from '@/components/common/empty-state';
import type { StatementImportOut } from '@/lib/api/types';

/**
 * 历史导入列表。
 *
 * **drift 适配:**
 * - 后端 `StatementImportOut` 没有 `status` 字段 —— 移除状态徽标列。
 * - 字段名走真实 backend schema:
 *   `imported_at`(原 `uploaded_at`)/ `raw_row_count`(原 `parsed_count`)/
 *   `deduped_count`(原 `duplicate_skipped_count`)/ `classified_count`(新增)。
 * - 加 `period_start ~ period_end` 列方便定位是哪段时间的账单。
 */
export function ImportHistory({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<StatementImportOut[] | null>(null);

  useEffect(() => {
    setItems(null);
    listStatements({ page: 1, limit: 20 })
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [refreshKey]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>历史导入</CardTitle>
      </CardHeader>
      <CardContent>
        {items === null && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        )}
        {items && items.length === 0 && <EmptyState title="还没有导入记录" />}
        {items && items.length > 0 && (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-40">时间</TableHead>
                  <TableHead>文件</TableHead>
                  <TableHead className="w-24">来源</TableHead>
                  <TableHead className="w-44">期间</TableHead>
                  <TableHead className="w-20 text-right">解析</TableHead>
                  <TableHead className="w-20 text-right">强重</TableHead>
                  <TableHead className="w-20 text-right">已分类</TableHead>
                  <TableHead className="w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="text-sm whitespace-nowrap">
                      {fmtDateTime(s.imported_at)}
                    </TableCell>
                    <TableCell className="max-w-xs truncate">
                      {s.filename}
                    </TableCell>
                    <TableCell className="text-sm">{s.source_type}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                      {s.period_start || s.period_end ? (
                        <>
                          {fmtDate(s.period_start)} ~ {fmtDate(s.period_end)}
                        </>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {s.raw_row_count}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {s.deduped_count}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {s.classified_count}
                    </TableCell>
                    <TableCell>
                      <Button asChild variant="ghost" size="icon">
                        <Link
                          href={`/statements/${s.id}/review`}
                          aria-label="查看复查页"
                        >
                          <Eye className="h-4 w-4" />
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
