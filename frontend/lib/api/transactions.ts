import { apiFetch } from './client';
import type { TransactionListOut, TransactionQuery } from './types';

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
