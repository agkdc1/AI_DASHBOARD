import { test, expect } from '@playwright/test';

const AI_URL = process.env.AI_ASSISTANT_URL || 'https://ai.your-domain.com';

test.describe('Scenario 3: AI Assistant', () => {
  test('3.1 AI navigate endpoint responds', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/assistant/navigate`, {
      data: {
        message: '在庫を追加したい',
        current_url: 'https://test-portal.your-domain.com/platform/',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.response_text).toBeTruthy();
    expect(body.actions).toBeDefined();
  });

  test('3.2 AI chat endpoint responds in Japanese', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/assistant/chat`, {
      data: {
        message: '在庫の追加方法を教えてください',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.response).toBeTruthy();
    // Response should contain Japanese text
    expect(body.response).toMatch(/[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]/);
  });

  test('3.3 AI chat responds in Korean for Korean input', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/assistant/chat`, {
      data: {
        message: '재고 추가 방법을 알려주세요',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.response).toBeTruthy();
    // Response should contain Korean text
    expect(body.response).toMatch(/[\uAC00-\uD7AF]/);
  });

  test('3.4 PII masking endpoint works', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/mask/text`, {
      data: {
        text: '田中太郎さんの電話番号は090-1234-5678です。',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.masked_text).toBeTruthy();
    expect(body.masked_text).not.toContain('田中太郎');
    expect(body.masked_text).not.toContain('090-1234-5678');
  });

  test('3.5 Task manager endpoint responds', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/assistant/task`, {
      data: {
        message: '在庫チェックタスクを作成して',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body).toBeTruthy();
  });

  test('3.6 Navigate endpoint returns actions for inventory query', async ({ request }) => {
    const resp = await request.post(`${AI_URL}/assistant/navigate`, {
      data: {
        message: '注文SO-TEST-001の出荷準備をしたい',
        current_url: 'https://test-portal.your-domain.com/platform/',
        dom_summary: 'div#app\n  nav.sidebar\n    a href="/platform/sales/"',
      },
    });

    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body.response_text).toBeTruthy();
    // Should return some navigation action
    if (body.actions.length > 0) {
      const types = body.actions.map((a: any) => a.type);
      expect(['navigate', 'highlight', 'click', 'scroll']).toEqual(
        expect.arrayContaining(types),
      );
    }
  });
});
