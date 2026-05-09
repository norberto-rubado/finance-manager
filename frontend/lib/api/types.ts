// 镜像 backend Pydantic schemas。Task 5 后会扩充各资源 schema。
// 为避免后续手动同步漂移,改 backend schema 后必须同步本文件(commit message 标 [sync types])。

export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}

export class ApiClientError extends Error {
  status: number;
  code: string;
  detail?: unknown;

  constructor(status: number, payload: ApiError) {
    super(payload.message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = payload.code;
    this.detail = payload.detail;
  }
}
