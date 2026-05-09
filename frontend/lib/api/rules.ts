import { apiFetch } from './client';
import type {
  MerchantRuleCreate,
  MerchantRuleOut,
  MerchantRuleUpdate,
} from './types';

/** 后端返 {items: MerchantRuleOut[], total: number}。
 *  Task 13 inline 写在这里(types.ts 未导出),Task 20 完整 CRUD 时如需扩展再统一。 */
export interface MerchantRuleListOut {
  items: MerchantRuleOut[];
  total: number;
}

/** GET /api/rules — 列表(无分页 query;后端返全量,默认按 priority 排序)。 */
export function listRules(): Promise<MerchantRuleListOut> {
  return apiFetch<MerchantRuleListOut>('/rules');
}

/** POST /api/rules — 新建。 */
export function createRule(body: MerchantRuleCreate): Promise<MerchantRuleOut> {
  return apiFetch<MerchantRuleOut>('/rules', { method: 'POST', body });
}

/** PATCH /api/rules/{id} — 改 pattern / match_kind / category_id / priority。 */
export function updateRule(
  id: number,
  body: MerchantRuleUpdate,
): Promise<MerchantRuleOut> {
  return apiFetch<MerchantRuleOut>(`/rules/${id}`, { method: 'PATCH', body });
}

/** DELETE /api/rules/{id} — 后端处理被引用情况,前端只关心 204。 */
export function deleteRule(id: number): Promise<void> {
  return apiFetch<void>(`/rules/${id}`, { method: 'DELETE' });
}
