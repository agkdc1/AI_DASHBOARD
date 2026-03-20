import { Page, expect } from '@playwright/test';

const TEST_USER = process.env.TEST_USER || 'admin';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'change-me';
const TEST_PORTAL_URL = process.env.TEST_PORTAL_URL || 'https://test-portal.your-domain.com';

/**
 * Login to InvenTree test portal with username/password.
 * InvenTree uses a React SPA (Mantine UI) — selectors differ from classic forms.
 */
export async function loginPortal(page: Page): Promise<void> {
  await page.goto(`${TEST_PORTAL_URL}/platform/login`);
  await page.waitForTimeout(3000);

  // InvenTree React login: look for any text input first, then password
  const usernameInput = page.locator('input[type="text"], input[name="username"], input[autocomplete="username"]').first();
  const passwordInput = page.locator('input[type="password"]').first();

  await usernameInput.waitFor({ timeout: 15_000 });
  await usernameInput.fill(TEST_USER);
  await passwordInput.fill(TEST_PASSWORD);

  // Submit — try button with login text or submit type
  const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("ログイン")').first();
  await submitBtn.click();

  // Wait for redirect away from login
  await page.waitForTimeout(5000);
}

/**
 * Get an API token for direct API calls.
 */
export async function getApiToken(): Promise<string> {
  // Use test-api (not test-portal) for API token
  const apiUrl = process.env.TEST_PORTAL_URL?.replace('test-portal', 'test-api') || 'https://test-api.your-domain.com';
  const resp = await fetch(`${apiUrl}/api/user/token/`, {
    headers: {
      Authorization: `Basic ${Buffer.from(`${TEST_USER}:${TEST_PASSWORD}`).toString('base64')}`,
    },
  });

  if (!resp.ok) throw new Error(`Auth failed: ${resp.status}`);
  const data = await resp.json();
  return data.token;
}

/**
 * Login to Flutter test app with username/password.
 * Flutter renders to canvas — cannot use HTML selectors.
 * Use page-level keyboard input instead.
 */
export async function loginFlutterApp(page: Page): Promise<void> {
  const testAppUrl = process.env.TEST_APP_URL || 'https://test-app.your-domain.com';
  await page.goto(testAppUrl);

  // Wait for Flutter to initialize
  await page.waitForTimeout(8000);

  // Flutter web renders as canvas or uses shadow DOM semantics
  // Try finding actual input elements first (Flutter TextField creates input elements)
  try {
    const inputs = page.locator('input');
    const count = await inputs.count();
    if (count >= 2) {
      await inputs.nth(0).fill(TEST_USER);
      await inputs.nth(1).fill(TEST_PASSWORD);
      // Find and click login button
      const button = page.locator('flt-semantics[role="button"]').first();
      if (await button.count() > 0) {
        await button.click();
      } else {
        await page.keyboard.press('Enter');
      }
    } else {
      // Fallback: use keyboard
      await page.keyboard.press('Tab');
      await page.keyboard.type(TEST_USER);
      await page.keyboard.press('Tab');
      await page.keyboard.type(TEST_PASSWORD);
      await page.keyboard.press('Enter');
    }
  } catch {
    // Last resort: just press Enter after typing
    await page.keyboard.type(TEST_USER);
    await page.keyboard.press('Tab');
    await page.keyboard.type(TEST_PASSWORD);
    await page.keyboard.press('Enter');
  }

  // Wait for home screen to load
  await page.waitForTimeout(8000);
}
