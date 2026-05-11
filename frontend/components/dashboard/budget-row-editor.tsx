'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { upsertBudget } from '@/lib/api/budgets';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categoryId: number;
  categoryName: string;
  periodYear: number;
  periodMonth: number;
  /** 当前已有预算金额(没设传 null) */
  currentAmount: string | null;
  /** 当前 note */
  currentNote: string | null;
  /** 成功保存后回调 */
  onSaved: () => void;
}

export function BudgetRowEditor({
  open,
  onOpenChange,
  categoryId,
  categoryName,
  periodYear,
  periodMonth,
  currentAmount,
  currentNote,
  onSaved,
}: Props) {
  const [amount, setAmount] = useState<string>('');
  const [note, setNote] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);

  // open 切换时同步 props 到本地 state
  useEffect(() => {
    if (open) {
      setAmount(currentAmount ?? '');
      setNote(currentNote ?? '');
    }
  }, [open, currentAmount, currentNote]);

  async function onSave() {
    const num = Number(amount);
    if (!Number.isFinite(num) || num < 0) {
      toast.error('请输入有效金额(>= 0)');
      return;
    }
    setSubmitting(true);
    try {
      await upsertBudget({
        period_year: periodYear,
        period_month: periodMonth,
        category_id: categoryId,
        amount: amount,
        note: note.trim() === '' ? null : note,
      });
      toast.success('保存成功');
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error('保存失败:' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>调整预算 — {categoryName}</DialogTitle>
          <DialogDescription>
            {periodYear} 年 {periodMonth} 月。设置为 0 等于本月不限。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1">
            <Label htmlFor="budget-amount">金额(¥)</Label>
            <Input
              id="budget-amount"
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="例:1500"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="budget-note">备注(可选)</Label>
            <Textarea
              id="budget-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={200}
              placeholder="例:含外卖,不含周末聚餐"
              rows={2}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={onSave} disabled={submitting}>
            {submitting ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
