/**
 * 格式化工具:金额 / 日期 / 百分比。
 * - 金额:本币 ¥ 默认,千分位,2 位小数;支持负数(支出红/收入绿在调用处控制 className)
 * - 日期:ISO yyyy-MM-dd(后端返这格式),展示按本地化 zh-CN
 * - 百分比:0.123 → "12.3%"(1 位小数)
 */

const CNY = new Intl.NumberFormat('zh-CN', {
  style: 'currency',
  currency: 'CNY',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const DEC = new Intl.NumberFormat('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function fmtMoney(
  amount: number | string | null | undefined,
  opts?: { withSign?: boolean; bare?: boolean },
): string {
  if (amount === null || amount === undefined || amount === '') return '—';
  const n = typeof amount === 'string' ? Number(amount) : amount;
  if (!Number.isFinite(n)) return '—';
  if (opts?.bare) return DEC.format(n);
  const formatted = CNY.format(n);
  if (opts?.withSign && n > 0) return '+' + formatted;
  return formatted;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  // backend 返 "2026-05-09" 或带时间 "2026-05-09T10:00:00"
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // 仅日期部分
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
    .format(d)
    .replace(/\//g, '-');
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
    .format(d)
    .replace(/\//g, '-');
}

export function fmtPercent(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) return '—';
  return (ratio * 100).toFixed(digits) + '%';
}

/** 文件大小(给上传提示用):1234 → "1.2 KB" */
export function fmtBytes(n: number): string {
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1024 / 1024).toFixed(1) + ' MB';
}
