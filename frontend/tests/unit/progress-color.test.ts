import { describe, expect, it } from 'vitest';
import { progressBgClass, progressTone } from '@/lib/utils/progress';

describe('progressTone', () => {
  it('budget=0 时返回 safe(防 div0)', () => {
    expect(progressTone(100, 0)).toBe('safe');
  });
  it('70% → safe', () => {
    expect(progressTone(70, 100)).toBe('safe');
  });
  it('80% → warn', () => {
    expect(progressTone(80, 100)).toBe('warn');
  });
  it('100% → warn(边界包含)', () => {
    expect(progressTone(100, 100)).toBe('warn');
  });
  it('101% → danger', () => {
    expect(progressTone(101, 100)).toBe('danger');
  });
});

describe('progressBgClass', () => {
  it('映射到 tailwind 类', () => {
    expect(progressBgClass('safe')).toContain('emerald');
    expect(progressBgClass('warn')).toContain('amber');
    expect(progressBgClass('danger')).toContain('rose');
  });
});
