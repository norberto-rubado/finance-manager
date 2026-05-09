import { test as base } from '@playwright/test';

interface Fixtures {
  loggedIn: void;
}

/**
 * `loggedIn` 是 auto fixture:每个 e2e test 跑前自动触发,
 * 走真实登录页 → 提交 admin 凭据 → 等待跳到 `/`,然后让 test 接手。
 *
 * 凭据来源:
 * - `ADMIN_TEST_USERNAME`(默认 `admin`)
 * - `ADMIN_TEST_PASSWORD`(必填,本地 dev 默认 `fm-dev-2026`,verify 脚本里 export)
 *
 * 没设密码就抛 —— 防止误把测试当成"我不需要登录的 e2e",静默走到 /login 再卡住。
 */
export const test = base.extend<Fixtures>({
  loggedIn: [
    async ({ page }, use) => {
      const username = process.env.ADMIN_TEST_USERNAME ?? 'admin';
      const password = process.env.ADMIN_TEST_PASSWORD;
      if (!password) {
        throw new Error('ADMIN_TEST_PASSWORD 未设;运行 e2e 必须设此环境变量');
      }
      await page.goto('/login');
      await page.getByLabel('用户名').fill(username);
      await page.getByLabel('密码').fill(password);
      await page.getByRole('button', { name: '登录' }).click();
      await page.waitForURL('/');
      await use();
    },
    { auto: true },
  ],
});

export { expect } from '@playwright/test';
