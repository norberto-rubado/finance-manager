'use client';

import { useEffect, useState } from 'react';
import { Filter as FilterIcon } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';

import { listAccounts } from '@/lib/api/accounts';
import { listCategories } from '@/lib/api/categories';
import type { AccountOut, CategoryOut } from '@/lib/api/types';

/**
 * 交易筛选面板的 FilterValues 形状。
 *
 * **Drift 说明(Task 12):**
 * - plan 原稿用 `search` + `amount_min/max`,但 backend(Task 5/11)用 `keyword`,且不支持金额过滤
 *   → 这里去掉 amount_*,把 search 改名为 keyword。
 * - `category_id === null` 是"未分类"哨兵,纯前端语义;后端 list 端点暂未接受 "null" 字符串
 *   (slice C 已知 gap),UI 留住状态等后端补丁。
 * - `include_mirror` 是 URL 友好语义(true = 含镜像);page.tsx 负责与 backend `is_mirror` 反向映射。
 */
export interface FilterValues {
  account_id?: number;
  category_id?: number | null;
  date_from?: string;
  date_to?: string;
  keyword?: string;
  include_mirror?: boolean;
}

/** 当前 FilterValues 上"非空"字段数,用于在按钮上显示 badge。 */
function countActive(v: FilterValues): number {
  let n = 0;
  if (v.account_id !== undefined) n++;
  if (v.category_id !== undefined) n++;
  if (v.date_from) n++;
  if (v.date_to) n++;
  if (v.keyword) n++;
  if (v.include_mirror) n++;
  return n;
}

// Radix Select 不允许 value=""(空字符串保留作内部 placeholder 状态);
// 我们用 __all__ / __none__ 作为哨兵。
const ALL = '__all__';
const NONE = '__none__';

function FilterFields({
  value,
  onChange,
  accounts,
  categories,
}: {
  value: FilterValues;
  onChange: (next: FilterValues) => void;
  accounts: AccountOut[];
  categories: CategoryOut[];
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="account_id">账户</Label>
        <Select
          value={
            value.account_id !== undefined ? String(value.account_id) : ALL
          }
          onValueChange={(v) =>
            onChange({
              ...value,
              account_id: v === ALL ? undefined : Number(v),
            })
          }
        >
          <SelectTrigger id="account_id">
            <SelectValue placeholder="全部" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部</SelectItem>
            {accounts.map((a) => (
              <SelectItem key={a.id} value={String(a.id)}>
                {a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="category_id">分类</Label>
        <Select
          value={
            value.category_id === null
              ? NONE
              : value.category_id !== undefined
                ? String(value.category_id)
                : ALL
          }
          onValueChange={(v) =>
            onChange({
              ...value,
              category_id:
                v === ALL ? undefined : v === NONE ? null : Number(v),
            })
          }
        >
          <SelectTrigger id="category_id">
            <SelectValue placeholder="全部" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部</SelectItem>
            <SelectItem value={NONE}>未分类</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-2">
          <Label htmlFor="date_from">起始日期</Label>
          <Input
            id="date_from"
            type="date"
            value={value.date_from ?? ''}
            onChange={(e) =>
              onChange({ ...value, date_from: e.target.value || undefined })
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="date_to">结束日期</Label>
          <Input
            id="date_to"
            type="date"
            value={value.date_to ?? ''}
            onChange={(e) =>
              onChange({ ...value, date_to: e.target.value || undefined })
            }
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="keyword">商家搜索</Label>
        <Input
          id="keyword"
          type="search"
          placeholder="按商家关键词模糊匹配"
          value={value.keyword ?? ''}
          onChange={(e) =>
            onChange({ ...value, keyword: e.target.value || undefined })
          }
        />
      </div>

      <div className="flex items-center gap-2">
        <Checkbox
          id="include_mirror"
          checked={Boolean(value.include_mirror)}
          onCheckedChange={(c) =>
            onChange({ ...value, include_mirror: Boolean(c) })
          }
        />
        <Label htmlFor="include_mirror" className="cursor-pointer">
          显示镜像交易
        </Label>
      </div>

      <Button
        type="button"
        variant="ghost"
        className="w-full"
        onClick={() => onChange({})}
      >
        清空筛选
      </Button>
    </div>
  );
}

/**
 * **TransactionFilter** — 双形态(桌面 sidebar + 手机 Sheet drawer)。
 *
 * 责任仅在 UI 层,所有状态由 page.tsx 通过 URL 同步管理。账户 / 分类列表在
 * 组件内部一次性拉取(纯只读字典),变化少。
 */
export function TransactionFilter({
  value,
  onChange,
}: {
  value: FilterValues;
  onChange: (next: FilterValues) => void;
}) {
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    Promise.all([
      listAccounts().catch(() => ({ items: [], total: 0 })),
      listCategories().catch(() => ({ items: [], total: 0 })),
    ]).then(([acc, cat]) => {
      setAccounts(acc.items);
      setCategories(cat.items);
    });
  }, []);

  const activeCount = countActive(value);

  return (
    <>
      {/* 桌面:左侧 sidebar(>= md)。 */}
      <aside className="hidden w-64 shrink-0 md:block">
        <div className="sticky top-4 rounded-md border bg-card p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold">筛选</h2>
            {activeCount > 0 && (
              <Badge variant="secondary">{activeCount}</Badge>
            )}
          </div>
          <FilterFields
            value={value}
            onChange={onChange}
            accounts={accounts}
            categories={categories}
          />
        </div>
      </aside>

      {/* 手机:触发按钮 + Sheet drawer(< md)。 */}
      <div className="md:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm">
              <FilterIcon className="mr-2 h-4 w-4" />
              筛选
              {activeCount > 0 && (
                <Badge variant="secondary" className="ml-2">
                  {activeCount}
                </Badge>
              )}
            </Button>
          </SheetTrigger>
          <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-sm">
            <SheetHeader>
              <SheetTitle>筛选</SheetTitle>
            </SheetHeader>
            <div className="mt-4">
              <FilterFields
                value={value}
                onChange={onChange}
                accounts={accounts}
                categories={categories}
              />
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
