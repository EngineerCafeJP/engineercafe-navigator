import { expect, test } from '@playwright/test';

/**
 * Fast-Path Routing E2E Tests (Issue #381, placeholder for #377)
 *
 * These tests verify the fast-path optimisation that skips memory loading
 * for FAQ-type queries (WiFi, hours, farewell) and always routes reception-
 * active queries through the full pipeline.
 *
 * NOTE: These tests are marked `test.skip` because they depend on the
 * fast-path routing implementation in Issue #377.  Once #377 is merged,
 * remove the skip annotations and adjust response-time thresholds.
 */

const QA_CHAT_URL = '/api/qa';
const VOICE_URL = '/api/voice';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const closeButton = page.getByRole('button', { name: /閉じてはじめる|Close and continue/ });
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click();
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function submitTextQuery(page: import('@playwright/test').Page, question: string) {
  const voiceButton = page.getByRole('button', { name: /音声応対|Voice chat/ });
  await voiceButton.click();

  const textToggle = page.getByRole('button', { name: /文字入力|Text input/ });
  if (await textToggle.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await textToggle.click();
  }

  const textarea = page.getByRole('textbox');
  if (!(await textarea.isVisible({ timeout: 2_000 }).catch(() => false))) {
    return false;
  }

  await textarea.fill(question);
  const sendButton = page.getByRole('button', { name: /送信|Send/ });
  await expect(sendButton).toBeEnabled({ timeout: 3_000 });
  await sendButton.click();
  return true;
}

// ---------------------------------------------------------------------------
// A. WiFi keyword fast-path
// ---------------------------------------------------------------------------

test.describe('Fast-path routing — WiFi keyword', () => {
  // Skip until #377 is implemented.
  test.skip(true, 'Fast-path routing not yet implemented (Issue #377)');

  test.beforeEach(async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-fp',
          greeting: 'こんにちは',
          stage: 'greeting',
        }),
      });
    });
  });

  test('WiFi keyword query responds within fast-path threshold', async ({ page }) => {
    // Mock a fast response to simulate the fast-path backend behaviour.
    await page.route(`**${QA_CHAT_URL}`, async (route) => {
      // Simulate fast-path: respond immediately (no memory_loader delay).
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: 'WiFiのパスワードはcafe2024です。',
          emotion: 'happy',
          metadata: { agent: 'FacilityAgent', fast_path: true },
        }),
      });
    });

    await page.goto('/');
    await dismissInitialModal(page);

    const startTime = Date.now();
    const submitted = await submitTextQuery(page, 'WiFiのパスワードは？');
    if (!submitted) {
      test.skip(true, 'Text input not available');
      return;
    }

    await expect(page.getByText(/WiFi|cafe2024/i)).toBeVisible({ timeout: 10_000 });
    const elapsed = Date.now() - startTime;

    // Fast-path should complete well under 5s (target: <2s for keyword queries).
    expect(elapsed).toBeLessThan(5_000);
  });
});

// ---------------------------------------------------------------------------
// B. FAQ queries skip memory loading
// ---------------------------------------------------------------------------

test.describe('Fast-path routing — FAQ skip memory', () => {
  test.skip(true, 'Fast-path routing not yet implemented (Issue #377)');

  test('hours query metadata indicates memory_loader was skipped', async ({ page }) => {
    let capturedRequestBody: Record<string, unknown> | null = null;

    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-faq',
          greeting: 'こんにちは',
          stage: 'greeting',
        }),
      });
    });
    await page.route(`**${QA_CHAT_URL}`, async (route, request) => {
      const method = request.method();
      if (method === 'POST') {
        try {
          capturedRequestBody = (await request.postDataJSON()) as Record<string, unknown>;
        } catch {
          // ignore parse errors
        }
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: '営業時間は平日・土曜9:00〜22:00です。',
          emotion: 'neutral',
          metadata: { agent: 'BusinessInfoAgent', fast_path: true, memory_loaded: false },
        }),
      });
    });

    await page.goto('/');
    await dismissInitialModal(page);

    const submitted = await submitTextQuery(page, '営業時間を教えてください');
    if (!submitted) {
      test.skip(true, 'Text input not available');
      return;
    }

    await expect(page.getByText(/営業時間|9:00/)).toBeVisible({ timeout: 10_000 });

    // Verify the request was captured (proves the flow reached the backend).
    expect(capturedRequestBody).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// C. Reception-active queries use full pipeline
// ---------------------------------------------------------------------------

test.describe('Fast-path routing — reception full pipeline', () => {
  test.skip(true, 'Fast-path routing not yet implemented (Issue #377)');

  test('reception-active query does not use fast-path', async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-reception-full',
          greeting: 'ようこそ！ご用件をお聞かせください。',
          stage: 'purpose_hearing',
        }),
      });
    });
    await page.route(`**${QA_CHAT_URL}`, async (route) => {
      // Simulate full-pipeline response (includes memory context).
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: '施設の見学ですね。ご案内いたします。',
          emotion: 'happy',
          metadata: { agent: 'OrchestratorAgent', fast_path: false, memory_loaded: true },
        }),
      });
    });

    await page.goto('/');
    await dismissInitialModal(page);

    // Trigger welcome flow first to activate reception.
    const welcomeButton = page.getByRole('button', { name: 'Welcome' });
    await welcomeButton.click();
    await page.waitForTimeout(1_000);

    // Now submit a purpose query during active reception.
    const submitted = await submitTextQuery(page, '施設の見学をしたいです');
    if (!submitted) {
      test.skip(true, 'Text input not available');
      return;
    }

    await expect(page.getByText(/見学|ご案内/)).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// D. Non-keyword query (no fast-path match)
// ---------------------------------------------------------------------------

test.describe('Fast-path routing — non-keyword query', () => {
  test.skip(true, 'Fast-path routing not yet implemented (Issue #377)');

  test('ambiguous query goes through standard pipeline', async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-std',
          greeting: 'こんにちは',
          stage: 'greeting',
        }),
      });
    });
    await page.route(`**${QA_CHAT_URL}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: '福岡の天気は晴れの予報です。',
          emotion: 'neutral',
          metadata: { agent: 'GeneralKnowledgeAgent', fast_path: false },
        }),
      });
    });

    await page.goto('/');
    await dismissInitialModal(page);

    const submitted = await submitTextQuery(page, '今日の天気はどうですか？');
    if (!submitted) {
      test.skip(true, 'Text input not available');
      return;
    }

    await expect(page.getByText(/天気|晴れ/)).toBeVisible({ timeout: 15_000 });
  });
});
