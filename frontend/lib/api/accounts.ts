import { apiFetch } from './client';
import type { AccountCreate, AccountOut, AccountUpdate } from './types';

/** 后端返 {items: AccountOut[], total: number}。
 *  Task 10 inline 写在这里(types.ts 未导出),Task 12 保留以避免改动面扩散。 */
export interface AccountListOut {
  items: AccountOut[];
  total: number;
}

export function listAccounts(): Promise<AccountListOut> {
  return apiFetch<AccountListOut>('/accounts');
}

/** POST /api/accounts — 新建账户。 */
export function createAccount(body: AccountCreate): Promise<AccountOut> {
  return apiFetch<AccountOut>('/accounts', { method: 'POST', body });
}

/** PATCH /api/accounts/{id} — 更新名称 / 机构 / 末四位 / 归档状态。 */
export function updateAccount(id: number, body: AccountUpdate): Promise<AccountOut> {
  return apiFetch<AccountOut>(`/accounts/${id}`, { method: 'PATCH', body });
}

/** DELETE /api/accounts/{id} — 后端可能拒绝(被交易引用),前端只关心 204。 */
export function deleteAccount(id: number): Promise<void> {
  return apiFetch<void>(`/accounts/${id}`, { method: 'DELETE' });
}
