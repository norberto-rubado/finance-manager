import type { ReadonlyURLSearchParams } from 'next/navigation';

/** 把 plain object 序列化为 search params,跳过 undefined / null / "" */
export function objectToSearchParams(obj: Record<string, unknown>): URLSearchParams {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === '') continue;
    if (Array.isArray(v)) {
      for (const item of v) {
        if (item !== undefined && item !== null && item !== '') sp.append(k, String(item));
      }
      continue;
    }
    sp.set(k, String(v));
  }
  return sp;
}

/** ReadonlyURLSearchParams → plain object(单值;数组用 getAll 单独读) */
export function searchParamsToObject(
  sp: ReadonlyURLSearchParams | URLSearchParams,
): Record<string, string> {
  const obj: Record<string, string> = {};
  sp.forEach((v, k) => {
    obj[k] = v;
  });
  return obj;
}

/** 安全 parseInt,失败回退 default */
export function parseIntSafe(v: string | null | undefined, defaultVal: number): number {
  if (v === null || v === undefined || v === '') return defaultVal;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : defaultVal;
}
