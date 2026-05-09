'use client';

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
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
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { createAccount, updateAccount } from '@/lib/api/accounts';
import type { AccountOut, AccountType } from '@/lib/api/types';

/**
 * **账户新建/编辑 dialog。**
 *
 * **Backend schema 适配(Task 5 drift,与 plan 原稿差异):**
 * - 字段名 `account_type` → backend `type`(7 值 → 5 值)
 * - 枚举去掉 `debit_card`/`credit_card`/`investment`/`other`,改用
 *   `bank_debit`/`bank_credit`/`alipay`/`wechat`/`cash`(spec § 数据模型)
 * - `last_four` → `last4`,`is_active` → `archived`(语义反转!checked = 停用)
 * - 移除 `current_balance`(后端无此字段,余额由交易聚合,不直接维护)
 * - 加入 `currency`(默认 CNY,大多数用户不会改)
 *
 * 编辑模式下展示"停用账户"Checkbox(语义直观:用户主动勾选才停用);
 * 新建模式不展示——新账户默认 archived=false 即活跃。
 */
const TYPES: { value: AccountType; label: string }[] = [
  { value: 'bank_debit', label: '银行借记卡' },
  { value: 'bank_credit', label: '银行信用卡' },
  { value: 'alipay', label: '支付宝' },
  { value: 'wechat', label: '微信' },
  { value: 'cash', label: '现金' },
];

const schema = z.object({
  name: z.string().min(1, '名称必填').max(100, '名称最多 100 字'),
  type: z.enum(['bank_debit', 'bank_credit', 'alipay', 'wechat', 'cash']),
  institution: z.string().max(100, '机构名最多 100 字').optional(),
  last4: z
    .string()
    .regex(/^\d{0,4}$/, '末 4 位为 0-4 位数字')
    .optional(),
  currency: z
    .string()
    .regex(/^[A-Z]{3}$/, '货币代码为 3 个大写字母,如 CNY')
    .default('CNY'),
  archived: z.boolean().default(false),
});

type Values = z.infer<typeof schema>;

const EMPTY_DEFAULTS: Values = {
  name: '',
  type: 'bank_debit',
  institution: '',
  last4: '',
  currency: 'CNY',
  archived: false,
};

export function AccountFormDialog({
  open,
  onOpenChange,
  initial,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initial: AccountOut | null; // null = 创建
  onSuccess: () => void;
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY_DEFAULTS,
  });

  // dialog 打开 / initial 切换 → reset 到当前账户值(或空白)
  useEffect(() => {
    if (!open) return;
    form.reset(
      initial
        ? {
            name: initial.name,
            type: initial.type,
            institution: initial.institution ?? '',
            last4: initial.last4 ?? '',
            currency: initial.currency,
            archived: initial.archived,
          }
        : EMPTY_DEFAULTS,
    );
  }, [open, initial, form]);

  const onSubmit = async (v: Values) => {
    try {
      if (initial) {
        // PATCH /accounts/{id}:仅传可变字段(后端 AccountUpdate 不接 type/currency)
        await updateAccount(initial.id, {
          name: v.name,
          institution: v.institution || null,
          last4: v.last4 || null,
          archived: v.archived,
        });
        toast.success('已更新');
      } else {
        await createAccount({
          name: v.name,
          type: v.type,
          institution: v.institution || null,
          last4: v.last4 || null,
          currency: v.currency,
        });
        toast.success('已创建');
      }
      onOpenChange(false);
      onSuccess();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? '编辑账户' : '新建账户'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>名称</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="如:招行储蓄卡" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>类型</FormLabel>
                  <Select
                    value={field.value}
                    onValueChange={field.onChange}
                    // 编辑模式禁用类型修改(后端 AccountUpdate 不接 type)
                    disabled={!!initial}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {TYPES.map((t) => (
                        <SelectItem key={t.value} value={t.value}>
                          {t.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-3">
              <FormField
                control={form.control}
                name="institution"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>开户机构</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="如:交通银行" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="last4"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>末 4 位</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder="1234"
                        maxLength={4}
                        inputMode="numeric"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="currency"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>货币</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      maxLength={3}
                      // 编辑模式禁用货币修改(后端 AccountUpdate 不接 currency)
                      disabled={!!initial}
                      placeholder="CNY"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {initial && (
              <FormField
                control={form.control}
                name="archived"
                render={({ field }) => (
                  <FormItem className="flex items-center space-x-2 space-y-0">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <FormLabel className="cursor-pointer">
                      停用账户(不再参与导入/统计)
                    </FormLabel>
                  </FormItem>
                )}
              />
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                取消
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? '保存中…' : '保存'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
