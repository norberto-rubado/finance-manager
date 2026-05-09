'use client';

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { listCategories } from '@/lib/api/categories';
import { patchTransaction } from '@/lib/api/transactions';
import { fmtDateTime, fmtMoney } from '@/lib/utils/fmt';
import type { CategoryOut, TransactionOut, TxKind } from '@/lib/api/types';

/**
 * **单条交易编辑 dialog。**
 *
 * **Backend schema 适配(Task 14 drift):**
 * 后端 `TransactionPatchIn` 仅接受 `category_id` 和 `tx_kind` —— plan 原稿想改的
 * `merchant_normalized` / `note` 后端不开放,因此:
 *
 * 1. **商家**只读展示在 DialogContent 顶部(用户能看,改不了;改商家需后端扩展)
 * 2. **note** 字段直接移除(`description_raw` 是导入原文,也只读)
 * 3. **tx_kind** Select 加进来作为分类方向覆盖手段(分类器误判退款/中性时有用)
 * 4. **category_id** Select 仍是主功能,带"未分类"选项(value="null" 哨兵)
 *
 * `TransactionOut` 上无 `account_name`,所以由 page.tsx 把 accountMap 传进来。
 */
const NONE = 'null'; // category_id 选 "未分类" 时的 Select value 哨兵

const schema = z.object({
  // 'null' → null;数字字符串 → number。Select 的 value 永远是字符串。
  category_id: z
    .union([z.coerce.number().int().positive(), z.literal(NONE)])
    .transform((v) => (v === NONE ? null : v)),
  tx_kind: z.enum(['expense', 'income', 'neutral', 'refund']),
});

type Values = z.infer<typeof schema>;

const TX_KIND_LABEL: Record<TxKind, string> = {
  expense: '支出',
  income: '收入',
  neutral: '中性(转账/还款)',
  refund: '退款',
};

export function TransactionEditDialog({
  tx,
  accountMap,
  onOpenChange,
  onSuccess,
}: {
  tx: TransactionOut | null;
  accountMap: Map<number, string>;
  onOpenChange: (open: boolean) => void;
  onSuccess: (updated: TransactionOut) => void;
}) {
  const [cats, setCats] = useState<CategoryOut[]>([]);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    // 占位 default —— useEffect 在 tx 切换时会 reset 到当前交易的真实值
    defaultValues: {
      category_id: null as unknown as Values['category_id'],
      tx_kind: 'expense',
    },
  });

  // dialog 打开 / tx 切换 —— 重置表单到当前交易值,并加载分类列表
  useEffect(() => {
    if (!tx) return;
    form.reset({
      // category_id null → NONE 哨兵字符串(Select 不接受 null)
      category_id: (tx.category_id === null
        ? NONE
        : tx.category_id) as unknown as Values['category_id'],
      tx_kind: tx.tx_kind,
    });
    listCategories()
      .then((r) => setCats(r.items))
      .catch(() => {});
  }, [tx, form]);

  const onSubmit = async (v: Values) => {
    if (!tx) return;
    try {
      const updated = await patchTransaction(tx.id, {
        category_id: v.category_id, // number | null(zod transform 后)
        tx_kind: v.tx_kind,
      });
      toast.success('已更新');
      onSuccess(updated);
      onOpenChange(false);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (!tx) {
    // 关闭状态不渲染 dialog 树:避免 Radix 因 DialogContent 缺 DialogTitle 报 a11y warning,
    // 也避免 useForm 在 tx 为 null 时 resolve 出未定义字段。Radix Dialog 已 unmount 内部 Portal。
    return null;
  }
  const open = true;

  const merchant = tx.merchant_normalized ?? tx.merchant_raw ?? '(无商家)';
  const accountLabel = accountMap.get(tx.account_id) ?? `账户#${tx.account_id}`;
  const amountNum = Number(tx.amount);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑交易</DialogTitle>
          <DialogDescription>
            {fmtDateTime(tx.tx_time)} · {accountLabel} · {fmtMoney(amountNum)}
          </DialogDescription>
        </DialogHeader>

        {/* 商家:只读展示(后端 PATCH 不接受 merchant_normalized) */}
        <p className="text-sm text-muted-foreground">
          商家:<span className="text-foreground">{merchant}</span>
        </p>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="category_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>分类</FormLabel>
                  <Select
                    value={
                      field.value === null || field.value === undefined
                        ? NONE
                        : String(field.value)
                    }
                    onValueChange={(v) =>
                      field.onChange(v === NONE ? NONE : Number(v))
                    }
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="选一个分类" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={NONE}>未分类</SelectItem>
                      {cats.map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="tx_kind"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>方向</FormLabel>
                  <Select
                    value={field.value}
                    onValueChange={(v) => field.onChange(v as TxKind)}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(
                        ['expense', 'income', 'neutral', 'refund'] as TxKind[]
                      ).map((k) => (
                        <SelectItem key={k} value={k}>
                          {TX_KIND_LABEL[k]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                取消
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? '提交中…' : '保存'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
