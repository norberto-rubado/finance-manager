import { ApiClientError, type ApiError } from './types';

type Json = object | unknown[] | string | number | boolean | null;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: Json | FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** 401 时是否跳 /login(默认 true);auth.login 自身设 false */
  redirectOn401?: boolean;
  signal?: AbortSignal;
}

const API_BASE = '/api';

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_BASE}${path}`, typeof window === 'undefined' ? 'http://localhost' : window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.pathname + url.search;
}

export async function apiFetch<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, redirectOn401 = true, signal } = opts;

  const isFormData = body instanceof FormData;
  const headers: Record<string, string> = {};
  if (!isFormData && body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(buildUrl(path, query), {
    method,
    headers,
    credentials: 'same-origin', // 同 origin cookie 自动带
    body: isFormData ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (res.status === 401 && redirectOn401 && typeof window !== 'undefined') {
    // 不在 /login 时才跳
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    // 仍抛错让上层 catch
  }

  if (!res.ok) {
    let payload: ApiError;
    try {
      const j = await res.json();
      // FastAPI 默认 {detail:...},也可能是我们自定义 {code,message,detail}
      if (typeof j === 'object' && j !== null && 'message' in j) {
        payload = j as ApiError;
      } else if (typeof j === 'object' && j !== null && 'detail' in j) {
        payload = { code: 'HTTP_' + res.status, message: String((j as { detail: unknown }).detail) };
      } else {
        payload = { code: 'HTTP_' + res.status, message: res.statusText };
      }
    } catch {
      payload = { code: 'HTTP_' + res.status, message: res.statusText };
    }
    throw new ApiClientError(res.status, payload);
  }

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    return (await res.json()) as T;
  }
  return undefined as T;
}
