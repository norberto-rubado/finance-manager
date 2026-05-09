'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

/**
 * 通用 destructive-confirm dialog。Task 18 账户删除首用,Task 19/20 分类/规则页继续复用。
 *
 * **用法语义:**
 * - `destructive=true` 时确认按钮显示红色 destructive variant(账户/分类/规则等不可逆操作)
 * - `onConfirm` 可返回 Promise:点击后按钮 disabled 直到 resolve,期间防重复点击
 * - 业务侧 toast.error(失败) 由调用方处理,本组件只负责 UI 与 awaiting
 *
 * 没把 Form/zod 引入是有意的:删除/归档不需要表单字段,保持组件 deps 最小。
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmText = '确认',
  destructive = false,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: string;
  confirmText?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
}) {
  const [pending, setPending] = useState(false);

  const handleConfirm = async () => {
    if (pending) return;
    setPending(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            取消
          </Button>
          <Button
            type="button"
            variant={destructive ? 'destructive' : 'default'}
            onClick={handleConfirm}
            disabled={pending}
          >
            {pending ? '处理中…' : confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
