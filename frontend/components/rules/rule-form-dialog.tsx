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

import { createRule, updateRule } from '@/lib/api/rules';
import { listCategories } from '@/lib/api/categories';
import type {
  CategoryOut,
  MerchantRuleCreate,
  MerchantRuleOut,
  MerchantRuleUpdate,
  RuleMatchKind,
} from '@/lib/api/types';

/**
 * **商家规则新建/编辑 dialog(Task 20)。**
 *
 * **Backend schema 适配(plan 原稿 drift):**
 * - `pattern_type` → `match_kind`(spec § rule schema 重命名)
 * - `match_kind` 枚举 4 值(plan 原稿 3 值):`exact / contains / regex / fuzzy`
 *   注意:与 dedup.match_kind(strong/bridge/conversation)同名但不同枚举,见 types.ts 注释
 * - 类型名 `MerchantRuleCreate` / `MerchantRuleUpdate`(plan 原稿 `*In` 后缀已弃用)
 * - 移除 `notes` 字段 —— 后端 schema 不含该字段,plan 原稿 spec 错位
 *
 * **marker rule 特殊设计(spec § slice A Rec #5):**
 * `is_marker` 是纯前端切换控件(不进 API body),勾选时 submit 提交 `category_id=null`,
 * 后端遇到 null 走"仅累加 hit_count、不改交易分类"的 marker 路径。
 * 编辑模式下从 `initial.category_id === null` 反推 is_marker 初值,确保编辑现有 marker 时
 * 默认勾选 + 分类下拉隐藏。
 */
const MATCH_KINDS: { value: RuleMatchKind; label: string }[] = [
  { value: 'exact', label: '精确' },
  { value: 'contains', label: '包含' },
  { value: 'regex', label: '正则' },
  { value: 'fuzzy', label: '模糊' },
];

const schema = z
  .object({
    pattern: z.string().min(1, '规则模式必填').max(200, '模式最多 200 字'),
    match_kind: z.enum(['exact', 'contains', 'regex', 'fuzzy']),
    is_marker: z.boolean().default(false),
    // 表单内部用 string:'' 表示未选,数字 id 字符串表示具体分类
    // submit 前根据 is_marker 决定是否传 null
    category_id: z.string().default(''),
    priority: z.coerce
      .number()
      .int()
      .min(1, '优先级 1-1000')
      .max(1000, '优先级 1-1000'),
  })
  .refine((v) => v.is_marker || v.category_id !== '', {
    message: '非 marker 规则必须选分类',
    path: ['category_id'],
  });

type Values = z.infer<typeof schema>;

const EMPTY_DEFAULTS: Values = {
  pattern: '',
  match_kind: 'contains',
  is_marker: false,
  category_id: '',
  priority: 100,
};

export function RuleFormDialog({
  open,
  onOpenChange,
  initial,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initial: MerchantRuleOut | null; // null = 创建
  onSuccess: () => void;
}) {
  const [cats, setCats] = useState<CategoryOut[]>([]);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY_DEFAULTS,
  });

  const isMarker = form.watch('is_marker');

  // dialog 打开 → 拉分类列表 + reset 到当前规则值(或空白)
  useEffect(() => {
    if (!open) return;
    listCategories()
      .then((r) => setCats(r.items))
      .catch(() => {
        // 分类拉取失败不阻断 dialog,只是分类下拉为空
      });
    form.reset(
      initial
        ? {
            pattern: initial.pattern,
            match_kind: initial.match_kind,
            is_marker: initial.category_id === null,
            category_id:
              initial.category_id === null ? '' : String(initial.category_id),
            priority: initial.priority,
          }
        : EMPTY_DEFAULTS,
    );
  }, [open, initial, form]);

  // 切到 marker 模式时清空 category(避免提交时残留旧值)
  useEffect(() => {
    if (isMarker) form.setValue('category_id', '');
  }, [isMarker, form]);

  const onSubmit = async (v: Values) => {
    try {
      const categoryId = v.is_marker ? null : Number(v.category_id);
      if (initial) {
        const body: MerchantRuleUpdate = {
          pattern: v.pattern,
          match_kind: v.match_kind,
          category_id: categoryId,
          priority: v.priority,
        };
        await updateRule(initial.id, body);
        toast.success('已更新');
      } else {
        const body: MerchantRuleCreate = {
          pattern: v.pattern,
          match_kind: v.match_kind,
          category_id: categoryId,
          priority: v.priority,
        };
        await createRule(body);
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
          <DialogTitle>{initial ? '编辑规则' : '新建规则'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="pattern"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>模式</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="如:星巴克 / .*咖啡.*" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-3">
              <FormField
                control={form.control}
                name="match_kind"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>匹配类型</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={field.onChange}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {MATCH_KINDS.map((m) => (
                          <SelectItem key={m.value} value={m.value}>
                            {m.label}
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
                name="priority"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>优先级(数字越小越先匹配)</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={1000}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="is_marker"
              render={({ field }) => (
                <FormItem className="flex items-center space-x-2 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <FormLabel className="cursor-pointer">
                    仅标记(marker rule,不分类只 hit_count++)
                  </FormLabel>
                </FormItem>
              )}
            />
            {!isMarker && (
              <FormField
                control={form.control}
                name="category_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>命中后归到分类</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={field.onChange}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="选一个分类" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
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
