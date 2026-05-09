import { apiFetch } from './client';
import type { SummaryGroupBy, SummaryOut, SummaryPeriod } from './types';

export interface SummaryQuery {
  period?: SummaryPeriod;
  date_from?: string;
  date_to?: string;
  group_by?: SummaryGroupBy;
}

export function getSummary(q: SummaryQuery = { period: 'month' }): Promise<SummaryOut> {
  return apiFetch<SummaryOut>('/summary', { query: { ...q } });
}
