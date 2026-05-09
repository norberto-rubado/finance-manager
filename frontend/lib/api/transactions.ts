import { apiFetch } from './client';
import type {
  BulkUpdateByMerchantIn,
  BulkUpdateResult,
  TransactionListOut,
  TransactionOut,
  TransactionPatchIn,
  TransactionQuery,
} from './types';

/**
 * GET /api/transactions
 * 后端用 limit + offset(非 page-based);is_mirror null 表示不过滤,
 * 因此调用方传 undefined 时直接不带该参数。
 * 注意:`category_id === null` 在 query 里需要序列化成字符串 "null",
 * 后端把它解释为"未分类"过滤;数字 id 直接传。
 */
export function listTransactions(q: TransactionQuery = {}): Promise<TransactionListOut> {
  return apiFetch<TransactionListOut>('/transactions', {
    query: {
      limit: q.limit,
      offset: q.offset,
      account_id: q.account_id,
      category_id: q.category_id === null ? 'null' : q.category_id,
      kind: q.kind,
      source: q.source,
      is_mirror: q.is_mirror,
      keyword: q.keyword,
      date_from: q.date_from,
      date_to: q.date_to,
    },
  });
}

/** GET /api/transactions/{id} — 详情。 */
export function getTransaction(id: number): Promise<TransactionOut> {
  return apiFetch<TransactionOut>(`/transactions/${id}`);
}

/** PATCH /api/transactions/{id} — 单条改 category_id / tx_kind。 */
export function patchTransaction(
  id: number,
  body: TransactionPatchIn,
): Promise<TransactionOut> {
  return apiFetch<TransactionOut>(`/transactions/${id}`, { method: 'PATCH', body });
}

/** POST /api/transactions/bulk-update-by-merchant — 按商家批量改分类(可顺手建规则)。 */
export function bulkUpdateByMerchant(
  body: BulkUpdateByMerchantIn,
): Promise<BulkUpdateResult> {
  return apiFetch<BulkUpdateResult>('/transactions/bulk-update-by-merchant', {
    method: 'POST',
    body,
  });
}

/** DELETE /api/transactions/{id} — 软删 / 硬删由后端决定;前端只关心 204。 */
export function deleteTransaction(id: number): Promise<void> {
  return apiFetch<void>(`/transactions/${id}`, { method: 'DELETE' });
}
