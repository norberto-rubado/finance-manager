import { apiFetch } from './client';
import type { AccountOut } from './types';

/** 后端返 {items: AccountOut[], total: number}。Task 12 会扩展 CRUD。 */
export interface AccountListOut {
  items: AccountOut[];
  total: number;
}

export function listAccounts(): Promise<AccountListOut> {
  return apiFetch<AccountListOut>('/accounts');
}
