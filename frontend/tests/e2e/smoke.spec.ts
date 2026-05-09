import { test, expect } from './fixtures';

/**
 * Slice D smoke:登录后 4 个核心场景能跑通就算 DoD 项 #5.smoke 过。
 * 真实端到端,需 backend `:8000` + Postgres + admin 用户已 seed。
 *
 * 不验数据正确性 — slice C 已有完整 import_flow.ps1 端到端覆盖业务正确性。
 * 本套只验 UI 路由 + 关键 widget 渲染没炸。
 */

test('home shows KPI cards after login', async ({ page }) => {
  await expect(page.getByRole('heading', { name: '本月概览' })).toBeVisible();
  await expect(page.getByText('本月支出')).toBeVisible();
  await expect(page.getByText('本月收入')).toBeVisible();
  await expect(page.getByText('净额')).toBeVisible();
  await expect(page.getByText('待审核')).toBeVisible();
});

test('navigate to transactions', async ({ page }) => {
  await page.goto('/transactions');
  await expect(page.getByRole('heading', { name: '交易' })).toBeVisible();
});

test('navigate to statements', async ({ page }) => {
  await page.goto('/statements');
  await expect(page.getByRole('heading', { name: '导入' })).toBeVisible();
  await expect(page.getByText(/拖拽账单文件/)).toBeVisible();
});

test('logout returns to login page', async ({ page }) => {
  await page.getByRole('button', { name: '用户菜单' }).click();
  await page.getByRole('menuitem', { name: /登出/ }).click();
  await page.waitForURL('/login');
});
