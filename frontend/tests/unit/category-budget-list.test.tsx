import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CategoryBudgetList } from '@/components/dashboard/category-budget-list';
import type { SnapshotCategory } from '@/lib/api/types';

function makeCat(overrides: Partial<SnapshotCategory>): SnapshotCategory {
  return {
    category_id: 1,
    name: '餐饮',
    icon: null,
    color: null,
    budget: null,
    spent: '0',
    three_month_avg: '0',
    note: null,
    is_overspending: false,
    ...overrides,
  };
}

describe('<CategoryBudgetList>', () => {
  it('类别预算未设时,显示 vs 均值', () => {
    const cats = [makeCat({ name: '餐饮', spent: '180', three_month_avg: '250' })];
    render(
      <CategoryBudgetList
        categories={cats}
        periodYear={2026}
        periodMonth={5}
        editable
        onSaved={() => {}}
      />,
    );
    expect(screen.getByText('餐饮')).toBeInTheDocument();
    expect(screen.getByText(/vs 均/)).toBeInTheDocument();
  });

  it('已设预算时,显示 spent / budget 格式', () => {
    const cats = [
      makeCat({
        name: '交通',
        spent: '320',
        budget: '1000',
        three_month_avg: '500',
      }),
    ];
    render(
      <CategoryBudgetList
        categories={cats}
        periodYear={2026}
        periodMonth={5}
        editable
        onSaved={() => {}}
      />,
    );
    // 数字会被 fmtMoney 格式化(带千分位),所以匹配子串
    expect(screen.getByText(/320/)).toBeInTheDocument();
    expect(screen.getByText(/1,000/)).toBeInTheDocument();
  });

  it('editable=false 时不渲染调整按钮', () => {
    const cats = [makeCat({ name: '餐饮' })];
    render(
      <CategoryBudgetList
        categories={cats}
        periodYear={2026}
        periodMonth={4}
        editable={false}
        onSaved={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: /调整/ })).toBeNull();
  });

  it('空数组时显示空态文案', () => {
    render(
      <CategoryBudgetList
        categories={[]}
        periodYear={2026}
        periodMonth={5}
        editable
        onSaved={() => {}}
      />,
    );
    expect(screen.getByText(/还没有支出类别/)).toBeInTheDocument();
  });
});
