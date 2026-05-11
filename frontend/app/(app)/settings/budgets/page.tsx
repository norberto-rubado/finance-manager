'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert } from '@/components/ui/alert';
import { ConfirmDialog } from '@/components/common/confirm-dialog';
import { CopyFromPrevButton } from '@/components/budgets/copy-from-prev-button';
import { MonthPicker, type MonthValue } from '@/components/dashboard/month-picker';
import { fmtMoney } from '@/lib/utils/fmt';

import { deleteBudget, listBudgets, upsertBudget } from '@/lib/api/budgets';
import { listCategories } from '@/lib/api/categories';
import type { BudgetOut, CategoryOut } from '@/lib/api/types';

export default function BudgetSettingsPage() {
  const [month, setMonth] = useState<MonthValue>(() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  });

  const [budgets, setBudgets] = useState<BudgetOut[] | null>(null);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const reload = useCallback(() => {
    setBudgets(null);
    Promise.all([
      listBudgets(month.year, month.month),
      listCategories().catch(() => ({ items: [], total: 0 })),
    ]).then(([bRes, cRes]) => {
      setBudgets(bRes);
      setCategories(cRes.items.filter((c) => c.kind === 'expense'));
    });
  }, [month]);

  useEffect(() => {
    reload();
  }, [reload]);

  const budgetByCat = new Map<number | null, BudgetOut>();
  for (const b of budgets ?? []) {
    budgetByCat.set(b.category_id, b);
  }

  const total = budgetByCat.get(null);
  const sumCat = (budgets ?? [])
    .filter((b) => b.category_id !== null)
    .reduce((s, b) => s + Number(b.amount), 0);
  const exceedsTotal = total !== undefined && sumCat > Number(total.amount);

  async function onSave(catId: number | null, amount: string, note: string | null) {
    try {
      await upsertBudget({
        period_year: month.year,
        period_month: month.month,
        category_id: catId,
        amount,
        note,
      });
      toast.success('保存成功');
      reload();
    } catch (e) {
      toast.error('保存失败:' + (e instanceof Error ? e.message : String(e)));
    }
  }

  async function onDelete(id: number) {
    try {
      await deleteBudget(id);
      toast.success('已删除');
      reload();
    } catch (e) {
      toast.error('删除失败:' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setDeletingId(null);
    }
  }

  if (budgets === null) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">预算管理</h1>
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">预算管理</h1>
          <p className="text-sm text-muted-foreground">
            <Link className="underline" href="/settings">
              ← 回到设置
            </Link>{' '}
            · 选择月份后设置总预算 + 各类别预算
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MonthPicker value={month} onChange={setMonth} />
          <CopyFromPrevButton year={month.year} month={month.month} onSuccess={reload} />
        </div>
      </div>

      {exceedsTotal && (
        <Alert variant="destructive">
          已设的类别预算总和 {fmtMoney(sumCat)} 已超过本月总预算 {fmtMoney(total!.amount)}
          。建议调整。
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>本月总预算</CardTitle>
        </CardHeader>
        <CardContent>
          <BudgetRow
            label="总预算"
            existing={total}
            onSave={(amt, note) => onSave(null, amt, note)}
            onDelete={total ? () => setDeletingId(total.id) : undefined}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>类别预算</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {categories.length === 0 ? (
            <p className="text-sm text-muted-foreground">还没有支出类别</p>
          ) : (
            categories.map((c) => (
              <BudgetRow
                key={c.id}
                label={c.name}
                existing={budgetByCat.get(c.id)}
                onSave={(amt, note) => onSave(c.id, amt, note)}
                onDelete={
                  budgetByCat.has(c.id)
                    ? () => setDeletingId(budgetByCat.get(c.id)!.id)
                    : undefined
                }
              />
            ))
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deletingId !== null}
        onOpenChange={(o) => {
          if (!o) setDeletingId(null);
        }}
        title="确认删除预算?"
        description="删除后,该项预算会从本月移除;dashboard 上对应类别将回退到'vs 历史均值'参考。"
        confirmText="删除"
        destructive
        onConfirm={() => {
          if (deletingId !== null) {
            return onDelete(deletingId);
          }
        }}
      />
    </div>
  );
}

function BudgetRow({
  label,
  existing,
  onSave,
  onDelete,
}: {
  label: string;
  existing: BudgetOut | undefined;
  onSave: (amount: string, note: string | null) => void;
  onDelete?: () => void;
}) {
  const [amount, setAmount] = useState<string>(existing?.amount ?? '');
  const [note, setNote] = useState<string>(existing?.note ?? '');
  const [dirty, setDirty] = useState(false);

  // 切换月份后,existing 变了 → 同步本地 state
  useEffect(() => {
    setAmount(existing?.amount ?? '');
    setNote(existing?.note ?? '');
    setDirty(false);
  }, [existing]);

  return (
    <div className="grid grid-cols-1 gap-2 rounded-md border p-3 md:grid-cols-[1fr_auto_auto_auto]">
      <Label className="md:self-center">{label}</Label>
      <div className="space-y-1">
        <Input
          type="number"
          inputMode="decimal"
          step="0.01"
          min="0"
          value={amount}
          onChange={(e) => {
            setAmount(e.target.value);
            setDirty(true);
          }}
          placeholder="¥"
          className="w-32"
        />
      </div>
      <Textarea
        value={note}
        onChange={(e) => {
          setNote(e.target.value);
          setDirty(true);
        }}
        maxLength={200}
        placeholder="备注(可选)"
        rows={1}
        className="md:w-64"
      />
      <div className="flex items-center gap-1">
        <Button
          size="sm"
          disabled={!dirty || amount === ''}
          onClick={() => {
            onSave(amount, note.trim() === '' ? null : note);
            setDirty(false);
          }}
        >
          保存
        </Button>
        {onDelete && (
          <Button size="icon" variant="ghost" onClick={onDelete} aria-label="删除预算">
            <Trash2 className="h-4 w-4 text-rose-500" />
          </Button>
        )}
      </div>
    </div>
  );
}
