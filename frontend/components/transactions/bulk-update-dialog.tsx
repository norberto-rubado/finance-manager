'use client';

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
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
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { listCategories } from '@/lib/api/categories';
import { bulkUpdateByMerchant } from '@/lib/api/transactions';
import type { CategoryOut } from '@/lib/api/types';

/**
 * **批量改类 dialog。**
 *
 * **Backend schema 适配(plan vs Task 5 backend):**
 * - plan 的 `merchant_normalized` → backend `pattern`(label 改为"匹配文本"更直观)
 * - plan 的 `also_create_rule` → backend `also_add_rule`
 * - 隐式默认 `match_kind: 'exact'`(MVP 不暴露选项;exact 是"按完整商家名批改"的安全语义,
 *   Task 20 规则 CRUD 才让用户精细控制 contains / regex / fuzzy)
 * - 结果字段 `affected_count` / `rule_id`(plan 原稿 `affected` / `rule_created_id` 已过时)
 */
const schema = z.object({
  pattern: z.string().min(1, '匹配文本必填'),
  category_id: z.coerce.number().int().positive('请选择分类'),
  also_add_rule: z.boolean().default(false),
});

type Values = z.infer<typeof schema>;

export function BulkUpdateDialog({
  open,
  onOpenChange,
  defaultMerchant,
  selectedCount,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultMerchant: string;
  selectedCount: number;
  onSuccess: () => void;
}) {
  const [cats, setCats] = useState<CategoryOut[]>([]);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      pattern: defaultMerchant,
      category_id: 0 as unknown as number,
      also_add_rule: false,
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        pattern: defaultMerchant,
        category_id: 0 as unknown as number,
        also_add_rule: false,
      });
      listCategories()
        .then((r) => setCats(r.items))
        .catch(() => {});
    }
  }, [open, defaultMerchant, form]);

  const onSubmit = async (v: Values) => {
    try {
      const res = await bulkUpdateByMerchant({
        pattern: v.pattern,
        match_kind: 'exact', // 隐藏字段:MVP 默认按精确匹配批改
        category_id: v.category_id,
        also_add_rule: v.also_add_rule,
      });
      toast.success(
        `已更新 ${res.affected_count} 条${res.rule_id ? ',规则已创建' : ''}`,
      );
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
          <DialogTitle>批量改类</DialogTitle>
          <DialogDescription>
            为商家 &ldquo;{defaultMerchant}&rdquo; 的 {selectedCount}{' '}
            条选中交易统一改分类。可选同时创建商家规则,以后自动归类同名交易。
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="space-y-4"
          >
            <FormField
              control={form.control}
              name="pattern"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>匹配文本(精确)</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="category_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>分类</FormLabel>
                  <Select
                    value={field.value ? String(field.value) : ''}
                    onValueChange={(v) => field.onChange(Number(v))}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="选一个分类" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {cats
                        .filter(
                          (c) => c.kind === 'expense' || c.kind === 'income',
                        )
                        .map((c) => (
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
              name="also_add_rule"
              render={({ field }) => (
                <FormItem className="flex items-center space-x-2 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <FormLabel className="cursor-pointer">
                    同时创建商家规则(以后自动归类)
                  </FormLabel>
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
                {form.formState.isSubmitting ? '提交中…' : '确认'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
