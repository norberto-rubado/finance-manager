import { apiFetch } from './client';
import type { BudgetCopyIn, BudgetIn, BudgetOut } from './types';

export function listBudgets(year: number, month: number): Promise<BudgetOut[]> {
  return apiFetch<BudgetOut[]>('/budgets', { query: { year, month } });
}

export function upsertBudget(body: BudgetIn): Promise<BudgetOut> {
  return apiFetch<BudgetOut>('/budgets', { method: 'PUT', body });
}

export function deleteBudget(id: number): Promise<void> {
  return apiFetch<void>(`/budgets/${id}`, { method: 'DELETE' });
}

export function copyBudgetsFrom(body: BudgetCopyIn): Promise<BudgetOut[]> {
  return apiFetch<BudgetOut[]>('/budgets/copy-from', { method: 'POST', body });
}
