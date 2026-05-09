'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';

import { EmptyState } from '@/components/common/empty-state';
import { Pagination } from '@/components/common/pagination';
import { TransactionTable } from '@/components/transactions/transaction-table';
import { Skeleton } from '@/components/ui/skeleton';

import { listAccounts } from '@/lib/api/accounts';
import { listCategories } from '@/lib/api/categories';
import { listTransactions } from '@/lib/api/transactions';
import { objectToSearchParams, parseIntSafe } from '@/lib/utils/query';
import type { TransactionOut, TransactionQuery } from '@/lib/api/types';

const DEFAULT_LIMIT = 50;

/**
 * 交易列表页(桌面表格 + 分页 + URL 同步)。
 *
 * Next.js App Router 的 `useSearchParams()` 必须包在 `<Suspense>` 里才能 SSG —— 否则 build 报
 * "missing-suspense-with-csr-bailout";所以把读 search params 的逻辑下沉到子组件。
 */
export default function TransactionsPage() {
  return (
    <Suspense fallback={<TransactionsSkeleton />}>
      <TransactionsView />
    </Suspense>
  );
}

function TransactionsSkeleton() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">交易</h1>
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    </div>
  );
}

/**
 * **URL ↔ filter ↔ backend 映射:**
 * - URL 是用户友好的 page-based(`?page=2&limit=50`),内部转 offset 调后端。
 * - URL `?include_mirror=true` → 显示镜像(`is_mirror: undefined` 不过滤)
 *   缺省 → 排除镜像(`is_mirror: false`)。
 * - URL `?category_id=null` 想表达"未分类":后端 list 端点暂不接受字符串 "null"
 *   (slice C 已知 gap),URL 状态保留但 API 调用时 drop —— Task 12 / 后端补丁解决。
 * - URL `?keyword=` 优先,兼容 `?search=` 过渡。
 *
 * Task 12 加筛选面板;Task 13 加手机卡片视图;Task 14 加编辑 dialog。
 */
function TransactionsView() {
  const router = useRouter();
  const sp = useSearchParams();

  const filter = useMemo(() => {
    const categoryRaw = sp.get('category_id');
    return {
      page: parseIntSafe(sp.get('page'), 1),
      limit: parseIntSafe(sp.get('limit'), DEFAULT_LIMIT),
      account_id: sp.get('account_id') ? Number(sp.get('account_id')) : undefined,
      // null 哨兵保留 URL 状态,但 API 调用时 drop(后端 list 暂不支持)
      category_id:
        categoryRaw === 'null'
          ? null
          : categoryRaw
            ? Number(categoryRaw)
            : undefined,
      date_from: sp.get('date_from') ?? undefined,
      date_to: sp.get('date_to') ?? undefined,
      keyword: sp.get('keyword') ?? sp.get('search') ?? undefined,
      // 缺省:排除镜像;include_mirror=true 时不过滤
      is_mirror: sp.get('include_mirror') === 'true' ? undefined : false,
    };
  }, [sp]);

  const [items, setItems] = useState<TransactionOut[] | null>(null);
  const [total, setTotal] = useState(0);
  const [accountMap, setAccountMap] = useState<Map<number, string>>(new Map());
  const [categoryMap, setCategoryMap] = useState<Map<number, string>>(new Map());
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // accounts / categories 一次性加载(数据变化少;Task 12 加筛选面板时复用)
  useEffect(() => {
    Promise.all([
      listAccounts().catch(() => ({ items: [], total: 0 })),
      listCategories().catch(() => ({ items: [], total: 0 })),
    ]).then(([accRes, catRes]) => {
      setAccountMap(new Map(accRes.items.map((a) => [a.id, a.name])));
      setCategoryMap(new Map(catRes.items.map((c) => [c.id, c.name])));
    });
  }, []);

  // transactions 跟随 filter 变化重抓
  useEffect(() => {
    setItems(null);
    setSelectedIds(new Set()); // 翻页 / 改筛选时清掉选中
    const offset = (filter.page - 1) * filter.limit;
    const apiQuery: TransactionQuery = {
      limit: filter.limit,
      offset,
      account_id: filter.account_id,
      // 后端不支持 "null" 字符串(已知 gap);只发数字 id
      category_id:
        typeof filter.category_id === 'number' ? filter.category_id : undefined,
      date_from: filter.date_from,
      date_to: filter.date_to,
      keyword: filter.keyword,
      is_mirror: filter.is_mirror,
    };
    listTransactions(apiQuery)
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((e: Error) => {
        toast.error('加载失败:' + e.message);
        setItems([]);
      });
  }, [filter]);

  const updateFilter = useCallback(
    (patch: Record<string, string | number | undefined>) => {
      const merged: Record<string, string | number | undefined> = {
        ...Object.fromEntries(sp.entries()),
        ...patch,
      };
      const search = objectToSearchParams(merged).toString();
      router.push(`/transactions${search ? '?' + search : ''}`);
    },
    [router, sp],
  );

  const onToggle = (id: number) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const onToggleAll = (checked: boolean) => {
    if (!items) return;
    setSelectedIds(checked ? new Set(items.map((t) => t.id)) : new Set());
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">交易</h1>
        {/* Task 12: 这里加筛选触发按钮 / Task 13: 加批量操作 bar */}
      </div>

      {items === null && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}

      {items && items.length === 0 && (
        <EmptyState title="无匹配交易" description="调整筛选条件,或先去导入账单" />
      )}

      {items && items.length > 0 && (
        <>
          {/* 桌面表格;Task 13 加手机卡片视图 */}
          <div className="hidden md:block">
            <TransactionTable
              items={items}
              accountMap={accountMap}
              categoryMap={categoryMap}
              selectedIds={selectedIds}
              onToggle={onToggle}
              onToggleAll={onToggleAll}
              onEdit={() => toast.info('Task 14 实现编辑 dialog')}
            />
          </div>
          <div className="md:hidden">
            <p className="text-sm text-muted-foreground">手机卡片视图 — Task 13 实现</p>
          </div>
          <Pagination
            page={filter.page}
            limit={filter.limit}
            total={total}
            onPageChange={(p) => updateFilter({ page: p })}
          />
        </>
      )}
    </div>
  );
}
