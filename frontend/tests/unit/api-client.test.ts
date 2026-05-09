import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '@/lib/api/client';
import { ApiClientError } from '@/lib/api/types';

const originalLocation = window.location;

beforeEach(() => {
  // 让 window.location.href 可写(jsdom 默认只读)
  Object.defineProperty(window, 'location', {
    writable: true,
    value: { ...originalLocation, pathname: '/transactions', href: '' },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(window, 'location', { writable: true, value: originalLocation });
});

describe('apiFetch', () => {
  it('GET 返回 JSON 体', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    const out = await apiFetch<{ ok: boolean }>('/health');
    expect(out).toEqual({ ok: true });
  });

  it('204 返回 undefined', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const out = await apiFetch('/auth/logout', { method: 'POST' });
    expect(out).toBeUndefined();
  });

  it('query 参数序列化进 URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    await apiFetch('/transactions', { query: { page: 2, limit: 50, undef: undefined } });
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain('page=2');
    expect(calledUrl).toContain('limit=50');
    expect(calledUrl).not.toContain('undef');
  });

  it('JSON body 自动加 Content-Type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    await apiFetch('/x', { method: 'POST', body: { a: 1 } });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(init.body).toBe('{"a":1}');
  });

  it('FormData 不加 Content-Type(浏览器自填 multipart boundary)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const fd = new FormData();
    fd.append('file', new Blob(['x']), 'a.csv');
    await apiFetch('/statements/import', { method: 'POST', body: fd });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });

  it('非 2xx 抛 ApiClientError 并保留 status/code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 'NOT_FOUND', message: 'tx 不存在' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    await expect(apiFetch('/transactions/999')).rejects.toMatchObject({
      name: 'ApiClientError',
      status: 404,
      code: 'NOT_FOUND',
      message: 'tx 不存在',
    });
  });

  it('FastAPI 默认 {detail} 格式也能解析', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Not authenticated' }), {
          status: 401,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    // 设 redirectOn401=false 避免本测试改 location
    await expect(apiFetch('/transactions', { redirectOn401: false })).rejects.toMatchObject({
      status: 401,
      message: 'Not authenticated',
    });
  });

  it('401 默认跳 /login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{"detail":"x"}', { status: 401, headers: { 'content-type': 'application/json' } })),
    );
    try {
      await apiFetch('/transactions');
    } catch {
      /* 仍会抛 */
    }
    expect(window.location.href).toBe('/login');
  });

  it('已经在 /login 时 401 不再跳', async () => {
    // Sentinel value 防止 false-positive:若 client 错误地执行了 redirect → href 会被覆盖为 '/login'
    // (跟 sentinel 不一致),即使新值刚好仍是 /login 也能识别出"被改写"了。
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, pathname: '/login', href: '/login?from=last' },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{"detail":"bad"}', { status: 401, headers: { 'content-type': 'application/json' } })),
    );
    try {
      await apiFetch('/auth/login', { method: 'POST', body: { username: 'x', password: 'y' } });
    } catch {
      /* swallow */
    }
    // sentinel 保留 → client 没改 href → 没跳
    expect(window.location.href).toBe('/login?from=last');
  });

  it('fetch reject 透传错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network failure')));
    await expect(apiFetch('/health')).rejects.toThrow('network failure');
  });
});
