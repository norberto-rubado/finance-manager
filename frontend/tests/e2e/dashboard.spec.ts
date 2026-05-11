import { test, expect } from './fixtures';

/**
 * Slice E e2e:dashboard 2 条核心 path。
 * 复用 fixtures.ts 的 loggedIn auto fixture(已自动登录 admin)。
 *
 * Path 1 — happy:进 dashboard → 改预算 → 数字变 → 刷新仍保留。
 * Path 2 — 时间窗:切到上月 → 月节奏卡消失 + 待办卡消失 + 累计图变整月。
 *
 * 真实端到端,需 backend `:8000` + 已 seed admin 用户 + ADMIN_TEST_PASSWORD env。
 */

test.describe('Dashboard happy path', () => {
  test('进 /dashboard 改一个类别预算后,数字立即变 + 刷新保留', async ({ page }) => {
    // 1. 跳到 dashboard
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

    // 2. 等类别列表加载
    await expect(page.getByText('类别预算')).toBeVisible();

    // 3. 找一个"调整 <name> 预算"按钮(任意类别,e2e 不挑特定类)。
    //    Slice E 把整行包成 button,aria-label 仍是 "调整 ... 预算" 格式。
    //    先在 click 之前拿到 aria-label,后面用来定位"被编辑的那一行",
    //    避免 /999/ 这种宽松正则误中页面其他位置的 ¥xx9.xx。
    const adjustButton = page.getByRole('button', { name: /^调整.*预算$/ }).first();
    const ariaLabel = await adjustButton.getAttribute('aria-label');
    expect(ariaLabel).toMatch(/^调整\s*(.+?)\s*预算$/);
    const categoryNameMatch = ariaLabel!.match(/^调整\s*(.+?)\s*预算$/);
    const categoryName = categoryNameMatch![1];

    await adjustButton.click();

    // 4. Dialog 出现
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText(/调整预算 —/)).toBeVisible();

    // 5. 输入金额(用 12345 这个独特数字,避免与页面已有 ¥9xx 冲突)
    const amountInput = page.getByLabel('金额(¥)');
    await amountInput.fill('12345');

    // 6. 点保存
    await page.getByRole('button', { name: '保存' }).click();

    // 7. Dialog 关闭 + toast 出现
    await expect(page.getByRole('dialog')).not.toBeVisible();
    await expect(page.getByText('保存成功')).toBeVisible();

    // 8. 在被编辑的那一行(通过 aria-label 精确定位)里出现 "12,345"
    //    fmtMoney 会输出 "12,345.00";为兼容潜在的格式差异允许逗号可选。
    const editedRow = page.getByRole('button', { name: `调整 ${categoryName} 预算` });
    await expect(editedRow).toContainText(/12,?345/);

    // 9. 刷新,值仍保留在同一行
    await page.reload();
    await expect(page.getByText('类别预算')).toBeVisible();
    const reloadedRow = page.getByRole('button', { name: `调整 ${categoryName} 预算` });
    await expect(reloadedRow).toContainText(/12,?345/);
  });
});

test.describe('Dashboard time-window switch', () => {
  test('切到上月 → 月节奏卡 + 待处理卡消失', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

    // 1. 验证本月时,节奏卡 + 待处理卡可见
    await expect(page.getByText('本月节奏')).toBeVisible();
    await expect(page.getByText('待处理')).toBeVisible();

    // 2. 打开 MonthPicker
    await page.getByRole('button', { name: '选择月份' }).click();

    // 3. 点击"上月"
    await page.getByRole('menuitem', { name: '上月' }).click();

    // 4. 等 URL 变化(出现 year/month)
    await page.waitForURL(/\/dashboard\?year=\d+&month=\d+/);

    // 5. 验证节奏卡 + 待处理卡消失(spec § 5.3)
    await expect(page.getByText('本月节奏')).not.toBeVisible();
    await expect(page.getByText('待处理')).not.toBeVisible();

    // 6. 累计支出图仍可见(变成整月)
    await expect(page.getByText('本月累计支出')).toBeVisible();

    // 7. 6 月趋势柱仍可见
    await expect(page.getByText('近 6 月支出趋势')).toBeVisible();
  });
});
