import { apiFetch } from './client';
import type {
  ImportResponse,
  ReviewBundle,
  StatementImportListOut,
  StatementImportOut,
} from './types';

/**
 * POST /api/statements/import — multipart 上传账单文件。
 * 后端通过 file 头四字节嗅探格式 + 路由到对应 parser(slice C)。
 */
export async function importStatement(file: File): Promise<ImportResponse> {
  const fd = new FormData();
  fd.append('file', file, file.name);
  return apiFetch<ImportResponse>('/statements/import', { method: 'POST', body: fd });
}

/**
 * GET /api/statements — 历史导入列表。
 * 对外是 page-based(1, 2, 3, …);后端用 limit/offset,内部转换。
 */
export function listStatements(
  query: { page?: number; limit?: number } = {},
): Promise<StatementImportListOut> {
  const limit = query.limit ?? 20;
  const offset = query.page ? (query.page - 1) * limit : 0;
  return apiFetch<StatementImportListOut>('/statements', {
    query: { limit, offset },
  });
}

/** GET /api/statements/{id} — 单条导入元信息(filename/source/period/统计)。 */
export function getStatement(id: number): Promise<StatementImportOut> {
  return apiFetch<StatementImportOut>(`/statements/${id}`);
}

/** GET /api/statements/{id}/review — 复查页一站式 bundle(Task 16 用)。 */
export function getReviewBundle(id: number): Promise<ReviewBundle> {
  return apiFetch<ReviewBundle>(`/statements/${id}/review`);
}
