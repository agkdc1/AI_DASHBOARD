import { defineConfig, devices } from '@playwright/test';

const TEST_PORTAL_URL = process.env.TEST_PORTAL_URL || 'https://test-portal.your-domain.com';
const TEST_APP_URL = process.env.TEST_APP_URL || 'https://test-app.your-domain.com';
const AI_ASSISTANT_URL = process.env.AI_ASSISTANT_URL || 'https://ai.your-domain.com';
const VIKUNJA_URL = process.env.VIKUNJA_URL || 'https://tasks.your-domain.com';
const OUTLINE_URL = process.env.OUTLINE_URL || 'https://wiki.your-domain.com';

export default defineConfig({
  testDir: './tests/scenarios',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,  // Scenarios depend on shared state
  forbidOnly: true,
  retries: 1,
  workers: 1,
  reporter: [
    ['html', { outputFolder: '/tmp/playwright-report', open: 'never' }],
    ['list'],
  ],
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: TEST_PORTAL_URL,
      },
    },
  ],
});

export { TEST_PORTAL_URL, TEST_APP_URL, AI_ASSISTANT_URL, VIKUNJA_URL, OUTLINE_URL };
