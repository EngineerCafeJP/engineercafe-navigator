import { expect, test } from '@playwright/test';

test.describe('API proxy', () => {
  test('GET /api/qa?action=health returns 200 JSON', async ({ request }) => {
    const response = await request.get('/api/qa?action=health');

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('success', true);
    expect(body).toHaveProperty('status', 'healthy');
  });

  test('POST /api/qa with valid body returns 200', async ({ request }) => {
    const response = await request.post('/api/qa', {
      data: {
        action: 'chat',
        question: 'テスト質問',
        sessionId: 'e2e-test-session',
        language: 'ja',
      },
    });

    // Backend may not be available in CI, so accept 200 or 502/503
    // but the route handler itself should not crash (no 500 from Next.js)
    expect([200, 502, 503]).toContain(response.status());

    const body = await response.json();
    expect(body).toBeDefined();
  });

  test('GET /api/qa without action param returns 400', async ({ request }) => {
    const response = await request.get('/api/qa');

    expect(response.status()).toBe(400);

    const body = await response.json();
    expect(body).toHaveProperty('error');
  });

  test('POST /api/qa with malformed JSON returns 400 or 500', async ({ request }) => {
    const response = await request.post('/api/qa', {
      headers: { 'Content-Type': 'application/json' },
      data: 'not valid json{{{',
    });

    expect([400, 500]).toContain(response.status());
  });
});
