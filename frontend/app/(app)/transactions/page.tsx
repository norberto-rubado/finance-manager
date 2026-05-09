'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';

import { EmptyState } from '@/components/common/empty-state';
import { Pagination } from '@/components/common/pagination';
import { BulkUpdateBar } from '@/components/transactions/bulk-update-bar';
import { BulkUpdateDialog } from '@/components/transactions/bulk-update-dialog';
import {
  TransactionFilterSidebar,
  TransactionFilterTrigger,
  type FilterValues,
} from '@/components/transactions/transaction-filter';
import { TransactionCards } from '@/components/transactions/transaction-cards';
import { TransactionEditDialog } from '@/components/transactions/transaction-edit-dialog';
import { TransactionTable } from '@/components/transactions/transaction-table';
import { Skeleton } from '@/components/ui/skeleton';

import { listAccounts } from '@/lib/api/accounts';
import { listCategories } from '@/lib/api/categories';
import { listTransactions } from '@/lib/api/transactions';
import { objectToSearchParams, parseIntSafe } from '@/lib/utils/query';
import type { TransactionOut, TransactionQuery } from '@/lib/api/types';

const DEFAULT_LIMIT = 50;

/**
 * 交易列表页(桌面表格 / 手机卡片 + 分页 + URL 同步 + 批量改类)。
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
 * Task 12 加筛选面板;Task 13 加手机卡片视图 + 批量改类 bar/dialog;Task 14 加编辑 dialog。
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

  // Task 13:批量改类 dialog 状态
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkDefaultMerchant, setBulkDefaultMerchant] = useState('');
  // Task 14:单条编辑 dialog —— 用 tx 对象本身做 open 哨兵(null = 关闭)
  const [editingTx, setEditingTx] = useState<TransactionOut | null>(null);
  // 触发 transactions 重抓的 key —— 改类成功后 +1 复用同一 useEffect,
  // 避免在 onBulkSuccess 里重复 URL→API query 转换逻辑(DRY)。
  const [refreshKey, setRefreshKey] = useState(0);

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

  // transactions 跟随 filter / refreshKey 变化重抓
  useEffect(() => {
    setItems(null);
    setSelectedIds(new Set()); // 翻页 / 改筛选 / 改类后清掉选中
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
  }, [filter, refreshKey]);

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

  // ============ Task 12: filter ↔ FilterValues 映射 ============
  // URL `is_mirror=false`(缺省)= 不含镜像;UI `include_mirror=true` = 含镜像。语义反转。
  const filterValues: FilterValues = {
    account_id: filter.account_id,
    category_id: filter.category_id,
    date_from: filter.date_from,
    date_to: filter.date_to,
    keyword: filter.keyword,
    include_mirror: filter.is_mirror === undefined,
  };

  const onFilterChange = (next: FilterValues) => {
    updateFilter({
      page: 1, // 改筛选回到第一页
      account_id: next.account_id,
      // null 哨兵走字符串 'null';数字 id 直传;undefined 表示不过滤(移除 URL key)
      category_id:
        next.category_id === null
          ? 'null'
          : next.category_id === undefined
            ? undefined
            : next.category_id,
      date_from: next.date_from,
      date_to: next.date_to,
      keyword: next.keyword,
      // include_mirror=true → URL `?include_mirror=true`;false → 移除 key(默认排除)
      include_mirror: next.include_mirror ? 'true' : undefined,
    });
  };

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

  // Task 13:批量改类 dialog 触发 / 成功后处理
  const selectedItems = useMemo(
    () => (items ?? []).filter((t) => selectedIds.has(t.id)),
    [items, selectedIds],
  );

  const onBulkOpen = (m: string) => {
    setBulkDefaultMerchant(m);
    setBulkOpen(true);
  };

  const onBulkSuccess = () => {
    setSelectedIds(new Set());
    // 触发同一 useEffect 重抓(避免重复 URL→API 转换逻辑)
    setRefreshKey((k) => k + 1);
  };

  // Task 14:单条编辑 ——
  // 成功后用 PATCH 返回的 updated 对象就地替换列表中的同 id 行,
  // 避免整页重抓(用户当前正在浏览的 filter / page 不变)。
  const onEdit = (tx: TransactionOut) => setEditingTx(tx);
  const onEditSuccess = (updated: TransactionOut) => {
    setItems((prev) =>
      prev ? prev.map((t) => (t.id === updated.id ? updated : t)) : prev,
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">交易</h1>
        {/* 手机:筛选触发按钮挂在 header 右侧,与 h1 视觉对齐(Task 13 polish A) */}
        <TransactionFilterTrigger
          value={filterValues}
          onChange={onFilterChange}
        />
      </div>

      {/* 桌面 sidebar + 内容双栏;手机 sidebar 自动 hidden(md:block 控制)。 */}
      <div className="flex gap-4">
        <TransactionFilterSidebar
          value={filterValues}
          onChange={onFilterChange}
        />
        <div className="min-w-0 flex-1 space-y-4">
          {items === null && (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          )}

          {items && items.length === 0 && (
            <EmptyState
              title="无匹配交易"
              description="调整筛选条件,或先去导入账单"
            />
          )}

          {items && items.length > 0 && (
            <>
              {/* 桌面表格 */}
              <div className="hidden md:block">
                <TransactionTable
                  items={items}
                  accountMap={accountMap}
                  categoryMap={categoryMap}
                  selectedIds={selectedIds}
                  onToggle={onToggle}
                  onToggleAll={onToggleAll}
                  onEdit={onEdit}
                />
              </div>
              {/* 手机卡片(Task 13) */}
              <div className="md:hidden">
                <TransactionCards
                  items={items}
                  accountMap={accountMap}
                  categoryMap={categoryMap}
                  selectedIds={selectedIds}
                  onToggle={onToggle}
                  onEdit={onEdit}
                />
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
      </div>

      {/* Task 13:底部批量操作 bar(selectedItems.length === 0 时返回 null) */}
      <BulkUpdateBar
        selectedItems={selectedItems}
        onClear={() => setSelectedIds(new Set())}
        onBulkUpdate={onBulkOpen}
      />
      <BulkUpdateDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        defaultMerchant={bulkDefaultMerchant}
        selectedCount={selectedItems.length}
        onSuccess={onBulkSuccess}
      />

      {/* Task 14:单条编辑 dialog —— editingTx 同时承担 open 哨兵 + 当前编辑对象 */}
      <TransactionEditDialog
        tx={editingTx}
        accountMap={accountMap}
        onOpenChange={(open) => {
          if (!open) setEditingTx(null);
        }}
        onSuccess={onEditSuccess}
      />
    </div>
  );
}
