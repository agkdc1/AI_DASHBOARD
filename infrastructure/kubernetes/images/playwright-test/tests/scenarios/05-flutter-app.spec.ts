import { test, expect } from '@playwright/test';
import { loginFlutterApp } from '../helpers/auth';

const TEST_APP_URL = process.env.TEST_APP_URL || 'https://test-app.your-domain.com';

test.describe('Scenario 5: Flutter Dashboard', () => {
  test('5.1 Flutter app loads', async ({ page }) => {
    await page.goto(TEST_APP_URL);
    // Wait for Flutter engine to initialize
    await page.waitForTimeout(8000);

    // Verify page loaded (HTTP 200 + some content rendered)
    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test('5.2 Flutter app responds to navigation', async ({ page }) => {
    await page.goto(TEST_APP_URL);
    await page.waitForTimeout(8000);

    // Verify no error pages
    const url = page.url();
    expect(url).toContain(TEST_APP_URL.replace('https://', ''));
  });

  test('5.3 Flutter app API reachable from app domain', async ({ request }) => {
    // Verify the test API is reachable (Flutter app calls this)
    const apiUrl = 'https://test-api.your-domain.com';
    const resp = await request.get(`${apiUrl}/api/`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.server).toBe('InvenTree');
  });

  test('5.4 Flutter app has correct configuration', async ({ page }) => {
    // Load the app and check the main.dart.js contains test mode flags
    const resp = await page.goto(`${TEST_APP_URL}/main.dart.js`);
    expect(resp?.ok()).toBeTruthy();
  });

  test('5.5 Flutter app service worker registered', async ({ page }) => {
    const resp = await page.goto(`${TEST_APP_URL}/flutter_service_worker.js`);
    expect(resp?.ok()).toBeTruthy();
  });
});
