'use client';

import { useState } from 'react';
import { UploadDropzone } from '@/components/statements/upload-dropzone';
import { ImportHistory } from '@/components/statements/import-history';

/**
 * 账单导入页 = 上传 dropzone + 历史导入列表。
 * 上传成功后 `refreshKey` 自增,触发历史列表重抓。
 */
export default function StatementsPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">导入</h1>
      <UploadDropzone onUploaded={() => setRefreshKey((k) => k + 1)} />
      <ImportHistory refreshKey={refreshKey} />
    </div>
  );
}
