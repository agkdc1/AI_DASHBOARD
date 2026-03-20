import { test, expect } from '@playwright/test';

const VIKUNJA_URL = process.env.VIKUNJA_URL || 'https://tasks.your-domain.com';
const OUTLINE_URL = process.env.OUTLINE_URL || 'https://wiki.your-domain.com';

test.describe('Scenario 6: Intranet Services (Vikunja + Outline)', () => {
  test('6.1 Vikunja loads and shows login page', async ({ page }) => {
    await page.goto(VIKUNJA_URL);
    await page.waitForTimeout(3000);

    // Vikunja should show login or redirect to OIDC
    const url = page.url();
    const body = await page.textContent('body');
    // Either shows Vikunja login page or redirected to Google OIDC
    expect(
      url.includes('tasks.your-domain.com') ||
      url.includes('accounts.google.com'),
    ).toBeTruthy();
    expect(body).toBeTruthy();
  });

  test('6.2 Vikunja API health check', async ({ request }) => {
    const resp = await request.get(`${VIKUNJA_URL}/api/v1/info`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.version).toBeTruthy();
    expect(body.frontend_url).toBeTruthy();
  });

  test('6.3 Outline loads and shows login page', async ({ page }) => {
    await page.goto(OUTLINE_URL);
    await page.waitForTimeout(3000);

    // Outline should show login or redirect to OIDC
    const url = page.url();
    const body = await page.textContent('body');
    expect(
      url.includes('wiki.your-domain.com') ||
      url.includes('accounts.google.com'),
    ).toBeTruthy();
    expect(body).toBeTruthy();
  });

  test('6.4 Outline API responds', async ({ request }) => {
    // Outline /api/auth.config returns OIDC config without auth
    const resp = await request.post(`${OUTLINE_URL}/api/auth.config`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.data).toBeTruthy();
  });

  test('6.5 Vikunja OIDC provider configured', async ({ request }) => {
    const resp = await request.get(`${VIKUNJA_URL}/api/v1/info`);
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    // Check auth methods available
    expect(body.auth).toBeDefined();
    expect(body.auth.openid_connect).toBeDefined();
    expect(body.auth.openid_connect.enabled).toBeTruthy();
  });
});
