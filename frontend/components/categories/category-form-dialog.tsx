'use client';

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
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

import { createCategory, updateCategory } from '@/lib/api/categories';
import type { CategoryOut } from '@/lib/api/types';

/**
 * **分类新建/编辑 dialog。**
 *
 * **Backend schema 适配(Task 5 drift,与 plan 原稿差异):**
 * - `kind` 枚举 3 值:`expense` / `income` / `neutral`(plan 原稿 `transfer` 为旧名,
 *   spec 已改为 `neutral` —— 表示既非支出也非收入,如内部转账、还款等)
 * - 类型名 `CategoryCreate` / `CategoryUpdate`(plan 原稿 `*In` 后缀已弃用)
 * - 新增 `color` 字段(后端 schema 已加),MVP 用纯文本输入(hex 或 named color),
 *   不引入完整 color picker
 * - `parent_id`:zod 的 union 改成更直接的 nullable + transform —— 表单内部用
 *   `'null'` 字面量代表"顶级",submit 前转回 number | null
 */
const KINDS: { value: 'expense' | 'income' | 'neutral'; label: string }[] = [
  { value: 'expense', label: '支出' },
  { value: 'income', label: '收入' },
  { value: 'neutral', label: '中性' },
];

const schema = z.object({
  name: z.string().min(1, '名称必填').max(50, '名称最多 50 字'),
  // 表单内部统一用 string:'null' 表示顶级,数字 id 字符串表示父分类
  // submit 时再转换成 number | null
  parent_id: z.string().default('null'),
  kind: z.enum(['expense', 'income', 'neutral']),
  icon: z.string().max(50, '图标最多 50 字').optional(),
  color: z.string().max(50, '颜色最多 50 字').optional(),
  sort_order: z.coerce.number().int().min(0, '排序为非负整数').default(0),
});

type Values = z.infer<typeof schema>;

const EMPTY_DEFAULTS: Values = {
  name: '',
  parent_id: 'null',
  kind: 'expense',
  icon: '',
  color: '',
  sort_order: 0,
};

export function CategoryFormDialog({
  open,
  onOpenChange,
  initial,
  parents,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initial: CategoryOut | null; // null = 创建
  parents: CategoryOut[]; // 顶级分类列表(parent_id === null)
  onSuccess: () => void;
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY_DEFAULTS,
  });

  // dialog 打开 / initial 切换 → reset 到当前分类值(或空白)
  useEffect(() => {
    if (!open) return;
    form.reset(
      initial
        ? {
            name: initial.name,
            parent_id:
              initial.parent_id === null ? 'null' : String(initial.parent_id),
            kind: initial.kind,
            icon: initial.icon ?? '',
            color: initial.color ?? '',
            sort_order: initial.sort_order,
          }
        : EMPTY_DEFAULTS,
    );
  }, [open, initial, form]);

  const onSubmit = async (v: Values) => {
    const parentId = v.parent_id === 'null' ? null : Number(v.parent_id);
    try {
      if (initial) {
        // PATCH: 后端 CategoryUpdate 不接 kind(分类类型创建后不可改)
        await updateCategory(initial.id, {
          name: v.name,
          parent_id: parentId,
          icon: v.icon || null,
          color: v.color || null,
          sort_order: v.sort_order,
        });
        toast.success('已更新');
      } else {
        await createCategory({
          name: v.name,
          parent_id: parentId,
          kind: v.kind,
          icon: v.icon || null,
          color: v.color || null,
          sort_order: v.sort_order,
        });
        toast.success('已创建');
      }
      onOpenChange(false);
      onSuccess();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  // 编辑模式下,parent 选择需排除自己(避免选自己作为父级)
  const parentOptions = initial
    ? parents.filter((p) => p.id !== initial.id)
    : parents;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? '编辑分类' : '新建分类'}</DialogTitle>
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
                    <Input {...field} placeholder="如:餐饮" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-3">
              <FormField
                control={form.control}
                name="kind"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>类别</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={field.onChange}
                      // 编辑模式禁用 kind 修改(后端 CategoryUpdate 不接 kind)
                      disabled={!!initial}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {KINDS.map((k) => (
                          <SelectItem key={k.value} value={k.value}>
                            {k.label}
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
                name="parent_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>父分类</FormLabel>
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
                        <SelectItem value="null">(顶级)</SelectItem>
                        {parentOptions.map((p) => (
                          <SelectItem key={p.id} value={String(p.id)}>
                            {p.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <FormField
                control={form.control}
                name="icon"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>图标</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="🍜 或 utensils" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="color"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>颜色</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="#FF6B6B 或 red" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
              control={form.control}
              name="sort_order"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>排序</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      type="number"
                      inputMode="numeric"
                      min={0}
                    />
                  </FormControl>
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
                {form.formState.isSubmitting ? '保存中…' : '保存'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
