import { apiFetch } from './client';
import type { LoginIn, LoginOut, MeOut } from './types';

export function login(body: LoginIn): Promise<LoginOut> {
  return apiFetch<LoginOut>('/auth/login', { method: 'POST', body, redirectOn401: false });
}

export function logout(): Promise<void> {
  return apiFetch<void>('/auth/logout', { method: 'POST' });
}

export function me(): Promise<MeOut> {
  return apiFetch<MeOut>('/auth/me');
}
