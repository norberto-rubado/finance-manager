import { apiFetch } from './client';
import type { CategoryCreate, CategoryOut, CategoryUpdate } from './types';

/** 后端返 {items: CategoryOut[], total: number}。
 *  Task 10 inline 写在这里(types.ts 未导出),Task 12 保留以避免改动面扩散。 */
export interface CategoryListOut {
  items: CategoryOut[];
  total: number;
}

export function listCategories(): Promise<CategoryListOut> {
  return apiFetch<CategoryListOut>('/categories');
}

/** POST /api/categories — 新建分类。 */
export function createCategory(body: CategoryCreate): Promise<CategoryOut> {
  return apiFetch<CategoryOut>('/categories', { method: 'POST', body });
}

/** PATCH /api/categories/{id} — 改名 / 父级 / 图标 / 颜色 / 排序。 */
export function updateCategory(id: number, body: CategoryUpdate): Promise<CategoryOut> {
  return apiFetch<CategoryOut>(`/categories/${id}`, { method: 'PATCH', body });
}

/** DELETE /api/categories/{id} — 后端处理被引用情况,前端只关心 204。 */
export function deleteCategory(id: number): Promise<void> {
  return apiFetch<void>(`/categories/${id}`, { method: 'DELETE' });
}
