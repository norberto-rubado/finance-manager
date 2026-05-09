import { apiFetch } from './client';
import type { CategoryOut } from './types';

/** 后端返 {items: CategoryOut[], total: number}。Task 12 会扩展 CRUD。 */
export interface CategoryListOut {
  items: CategoryOut[];
  total: number;
}

export function listCategories(): Promise<CategoryListOut> {
  return apiFetch<CategoryListOut>('/categories');
}
