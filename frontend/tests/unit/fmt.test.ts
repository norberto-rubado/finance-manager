import { describe, expect, it } from 'vitest';
import { fmtMoney, fmtDate, fmtDateTime, fmtPercent, fmtBytes } from '@/lib/utils/fmt';

describe('fmtMoney', () => {
  it('正数千分位 + ¥', () => {
    expect(fmtMoney(1234.5)).toBe('¥1,234.50');
  });
  it('负数', () => {
    expect(fmtMoney(-99.9)).toBe('-¥99.90');
  });
  it('null/undefined/空串 → "—"', () => {
    expect(fmtMoney(null)).toBe('—');
    expect(fmtMoney(undefined)).toBe('—');
    expect(fmtMoney('')).toBe('—');
  });
  it('字符串数字也接受', () => {
    expect(fmtMoney('100.5')).toBe('¥100.50');
  });
  it('bare 模式无符号', () => {
    expect(fmtMoney(1234.5, { bare: true })).toBe('1,234.50');
  });
  it('withSign 加 + 号(正数)', () => {
    expect(fmtMoney(50, { withSign: true })).toBe('+¥50.00');
  });
});

describe('fmtDate', () => {
  it('ISO date', () => {
    expect(fmtDate('2026-05-09')).toBe('2026-05-09');
  });
  it('null → "—"', () => {
    expect(fmtDate(null)).toBe('—');
  });
});

describe('fmtDateTime', () => {
  it('包含时分', () => {
    const out = fmtDateTime('2026-05-09T14:30:00');
    expect(out).toContain('2026-05-09');
    expect(out).toContain('14:30');
  });
});

describe('fmtPercent', () => {
  it('0.1234 → "12.3%"', () => {
    expect(fmtPercent(0.1234)).toBe('12.3%');
  });
  it('指定位数', () => {
    expect(fmtPercent(0.5, 0)).toBe('50%');
  });
});

describe('fmtBytes', () => {
  it('B / KB / MB', () => {
    expect(fmtBytes(500)).toBe('500 B');
    expect(fmtBytes(2048)).toBe('2.0 KB');
    expect(fmtBytes(5 * 1024 * 1024)).toBe('5.0 MB');
  });
});
