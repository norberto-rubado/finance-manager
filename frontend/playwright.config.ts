import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for slice D smoke E2E.
 *
 * - 单 admin 用户串行 (`fullyParallel: false`),避免多 worker 同 cookie 抢占。
 * - `webServer` 复用已起的 dev server (`reuseExistingServer: true`):本地开发时
 *   `pnpm dev` 已经在 :3000 跑就直接接,CI 单跑测试时自动起一个。
 * - 单 desktop project (1280x800),slice D DoD 不要求多端 e2e —— 手机布局靠 Vitest
 *   组件测试 + Lighthouse 截图覆盖。
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
