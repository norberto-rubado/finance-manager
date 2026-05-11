import { describe, expect, it } from 'vitest';

import { paceDescriptor } from '@/components/dashboard/month-pace-card';

describe('paceDescriptor', () => {
  it('null delta → 占位', () => {
    expect(paceDescriptor(null).text).toBe('—');
  });
  it('+15% → 提前(rose)', () => {
    const r = paceDescriptor(15);
    expect(r.text).toContain('提前');
    expect(r.tone).toContain('rose');
  });
  it('-15% → 落后(emerald)', () => {
    const r = paceDescriptor(-15);
    expect(r.text).toContain('落后');
    expect(r.tone).toContain('emerald');
  });
  it('±10% 以内 → 正常', () => {
    expect(paceDescriptor(5).text).toBe('正常节奏');
    expect(paceDescriptor(-5).text).toBe('正常节奏');
  });
});
