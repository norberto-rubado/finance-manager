import { apiFetch } from './client';
import type { LoginIn, LoginOut, MeOut } from './types';

export function login(body: LoginIn): Promise<LoginOut> {
  return apiFetch<LoginOut>('/auth/login', { method: 'POST', body, redirectOn401: false });
}

export function logout(): Promise<void> {
  return apiFetch<void>('/auth/logout', { method: 'POST' });
}

/**
 * 取当前登录用户。
 *
 * `opts.redirectOn401`(Task 22 polish):透传给底层 `apiFetch`。
 * UserMenu 这种"挂在 layout 顶部、用户已登录的页面才会渲染"的探测点,
 * 不应该被 401 触发跳转(默认行为)—— 否则在 token 刚刚过期时会与 layout 上的
 * 路由守卫互相打架。调用方传 `{ redirectOn401: false }` 显式接管错误处理。
 */
export function me(opts: { redirectOn401?: boolean } = {}): Promise<MeOut> {
  return apiFetch<MeOut>('/auth/me', { redirectOn401: opts.redirectOn401 });
}
