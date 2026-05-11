import { apiFetch } from './client';
import type { DashboardSnapshot } from './types';

/** client_date 必传:YYYY-MM-DD 格式的本地时区"今天"。 */
export function getDashboardSnapshot(
  year: number,
  month: number,
  clientDate: string,
): Promise<DashboardSnapshot> {
  return apiFetch<DashboardSnapshot>('/dashboard/snapshot', {
    query: { year, month, client_date: clientDate },
  });
}
