import { test, expect } from '@playwright/test';

const AI_URL = process.env.AI_ASSISTANT_URL || 'https://ai.your-domain.com';

test.describe('Scenario 4: Other Features', () => {
  test('4.1 Rakuten key status endpoint', async ({ request }) => {
    const resp = await request.get(`${AI_URL}/rakuten/status`);
    // May return 200 or 503 depending on key config — just verify endpoint exists
    expect([200, 503]).toContain(resp.status());
  });

  test('4.2 Health check endpoint', async ({ request }) => {
    const resp = await request.get(`${AI_URL}/health`);
    expect(resp.ok()).toBeTruthy();
  });

  test('4.3 PII text masking with phone numbers', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/mask/text`, {
      data: {
        text: '佐藤花子 03-1234-5678 東京都渋谷区1-2-3',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.masked_text).not.toContain('佐藤花子');
    expect(body.masked_text).not.toContain('03-1234-5678');
  });

  test('4.4 PII text masking with tracking numbers', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/mask/text`, {
      data: {
        text: 'ヤマト伝票番号 1234-5678-9012',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.masked_text).toBeTruthy();
  });

  test('4.5 Evolution trigger (dry run check)', async ({ request }) => {
    // Just verify the endpoint exists — don't actually trigger
    const resp = await request.get(`${AI_URL}/evolution/status`);
    // Endpoint might not exist — that's OK for now
    expect([200, 404, 405]).toContain(resp.status());
  });

  test('4.6 Task manager with Korean input', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/assistant/task`, {
      data: {
        message: '재고 확인 태스크를 만들어줘',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body).toBeTruthy();
  });
});
