/**
 * 类别预算进度条颜色阈值(spec § 5.5):
 *   ratio < 0.8 → emerald(还剩很多)
 *   0.8 <= ratio <= 1.0 → amber(吃紧)
 *   ratio > 1.0 → rose(超了)
 */
export type ProgressTone = 'safe' | 'warn' | 'danger';

export function progressTone(spent: number, budget: number): ProgressTone {
  if (budget <= 0) return 'safe';
  const r = spent / budget;
  if (r > 1) return 'danger';
  if (r >= 0.8) return 'warn';
  return 'safe';
}

export function progressBgClass(tone: ProgressTone): string {
  if (tone === 'danger') return 'bg-rose-500';
  if (tone === 'warn') return 'bg-amber-500';
  return 'bg-emerald-500';
}
