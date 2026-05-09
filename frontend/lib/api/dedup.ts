import { apiFetch } from './client';
import type { DedupPairOut, PendingPairListOut } from './types';

/**
 * GET /api/dedup/pending — 全局待审核去重对(分页 limit/offset)。
 *
 * **drift:** 后端 `/dedup/pending` 只接受 `limit` 和 `offset`,**不支持** `import_id` 过滤。
 * Review 页用 `bundle.pending_pairs`(后端已按 import 过滤),不会调本函数。
 * 此函数留作未来全局去重审核入口的占位。
 */
export function listPending(
  query: { limit?: number; offset?: number } = {},
): Promise<PendingPairListOut> {
  return apiFetch<PendingPairListOut>('/dedup/pending', { query });
}

/**
 * POST /api/dedup/{pair_id}/confirm — 确认这对是同一笔(mark mirror)。
 *
 * **drift:** 后端要求 body `{ action: 'confirm', note?: string | null }`(`DedupDecisionIn`)。
 * 走纯 confirm 路径时硬编码 action='confirm',note 暂不暴露。
 */
export function confirmPair(pairId: number): Promise<DedupPairOut> {
  return apiFetch<DedupPairOut>(`/dedup/${pairId}/confirm`, {
    method: 'POST',
    body: { action: 'confirm' },
  });
}

/**
 * POST /api/dedup/{pair_id}/reject — 否认这对是同一笔(unmark mirror)。
 *
 * **drift:** 后端 reject 端点是语法糖,签名不接受 body。
 */
export function rejectPair(pairId: number): Promise<DedupPairOut> {
  return apiFetch<DedupPairOut>(`/dedup/${pairId}/reject`, { method: 'POST' });
}
