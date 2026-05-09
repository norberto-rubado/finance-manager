'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CloudUpload, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { importStatement } from '@/lib/api/statements';
import { fmtBytes } from '@/lib/utils/fmt';
import { cn } from '@/lib/utils/cn';

const ACCEPT = '.csv,.xlsx,.pdf';
const MAX_BYTES = 50 * 1024 * 1024; // 50MB(spec § 4.7 上限)

/**
 * 拖拽 / 点选上传账单。
 *
 * **drift 适配:** 后端 `ImportResponse` 字段名与早期 plan 不同 —
 * 用 `raw_row_count`(解析行数) / `classified_count`(自动归类) /
 * `deduped_strong_count`(强重复跳过) / `dedup_pending_count`(待审核)。
 *
 * 上传成功后跳转 `/statements/{id}/review`(Task 16 实化)。
 */
export function UploadDropzone({ onUploaded }: { onUploaded: () => void }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  const upload = async (file: File) => {
    if (file.size > MAX_BYTES) {
      toast.error(`文件超过 ${fmtBytes(MAX_BYTES)} 上限`);
      return;
    }
    setBusy(true);
    try {
      const res = await importStatement(file);
      toast.success(
        `解析 ${res.raw_row_count} 条,自动归类 ${res.classified_count},跳过强重复 ${res.deduped_strong_count},待审核 ${res.dedup_pending_count} 对`,
      );
      router.push(`/statements/${res.import_id}/review`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
      onUploaded();
    }
  };

  const onPick = () => inputRef.current?.click();

  return (
    <Card>
      <CardContent
        className={cn(
          'flex flex-col items-center justify-center gap-3 border-2 border-dashed py-12 transition-colors',
          over ? 'border-primary bg-primary/5' : 'border-muted',
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) void upload(f);
        }}
      >
        {busy ? (
          <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" />
        ) : (
          <CloudUpload className="h-10 w-10 text-muted-foreground" />
        )}
        <div className="space-y-1 text-center">
          <p className="font-medium">
            {busy ? '正在解析…' : '拖拽账单文件到此或点击选择'}
          </p>
          <p className="text-xs text-muted-foreground">
            支持 支付宝 CSV / 微信 xlsx / 交行 PDF / 建行信用卡 PDF;单文件 ≤{' '}
            {fmtBytes(MAX_BYTES)}
          </p>
        </div>
        <Button onClick={onPick} disabled={busy}>
          选择文件
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
            e.target.value = '';
          }}
        />
      </CardContent>
    </Card>
  );
}
