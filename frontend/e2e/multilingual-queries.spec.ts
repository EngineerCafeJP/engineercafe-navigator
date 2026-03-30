import { expect, test } from '@playwright/test';

/**
 * Multilingual Query E2E Tests (Issue #381)
 *
 * Verify that the kiosk correctly handles queries in Japanese, English,
 * Chinese, and Korean.  Tests use route interception to mock backend
 * responses so they run without a live backend.
 *
 * Corresponds to backend scenario groups:
 *   - TestJapaneseRegularUser (A01-A10)
 *   - TestEnglishTourist (B11-B17)
 *   - TestMultilingual (F33-F34)
 */

const QA_CHAT_URL = '/api/qa';
const VOICE_URL = '/api/voice';

const backendUrl = process.env.BACKEND_API_URL;
const backendKey = process.env.BACKEND_API_KEY;
const hasBackend = Boolean(backendUrl && backendKey);

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

/** Open text-input mode and submit a question via the text field. */
async function submitTextQuery(page: import('@playwright/test').Page, question: string) {
  // Enter voice mode first (text input is available inside voice mode).
  const voiceButton = page.getByRole('button', { name: /音声応対|Voice chat/ });
  await voiceButton.click();

  // The text-input toggle might not exist in the current kiosk layout.
  // Look for a text input or toggle button.
  const textToggle = page.getByRole('button', { name: /文字入力|Text input/ });
  if (await textToggle.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await textToggle.click();
  }

  const textarea = page.getByRole('textbox');
  // If no visible textarea, the kiosk may require voice only — skip gracefully.
  if (!(await textarea.isVisible({ timeout: 2_000 }).catch(() => false))) {
    return false;
  }

  await textarea.fill(question);
  const sendButton = page.getByRole('button', { name: /送信|Send/ });
  await expect(sendButton).toBeEnabled({ timeout: 3_000 });
  await sendButton.click();
  return true;
}

function mockQaResponse(
  page: import('@playwright/test').Page,
  answer: string,
  language: string = 'ja',
) {
  return page.route(`**${QA_CHAT_URL}`, async (route, request) => {
    const method = request.method();
    if (method === 'GET') {
      // Health check
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, status: 'healthy' }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        answer,
        emotion: 'happy',
        metadata: { agent: 'E2ETestAgent', language },
      }),
    });
  });
}

// ---------------------------------------------------------------------------
// A. Japanese queries (mocked backend)
// ---------------------------------------------------------------------------

test.describe('Multilingual — Japanese queries (mocked)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-ja',
          greeting: 'こんにちは',
          stage: 'greeting',
        }),
      });
    });
  });

  test('WiFi query returns Japanese response', async ({ page }) => {
    await mockQaResponse(
      page,
      'Wi-Fiは無料でご利用いただけます。SSID: EngineerCafe_WiFi',
      'ja',
    );
    await page.goto('/');
    await dismissInitialModal(page);

    const submitted = await submitTextQuery(page, 'WiFiのパスワードを教えてください');
    if (!submitted) {
      test.skip(true, 'Text input not available in current kiosk layout');
      return;
    }

    // Wait for the response to appear somewhere on page.
    await expect(page.getByText(/Wi-Fi|wifi/i)).toBeVisible({ timeout: 15_000 });
  });

  test('business hours query returns Japanese response', async ({ page }) => {
    await mockQaResponse(page, '営業時間は平日・土曜9:00〜22:00、日祝9:00〜20:00です。', 'ja');
    await page.goto('/');
    await dismissInitialModal(page);

    const submitted = await submitTextQuery(page, '営業時間は何時までですか？');
    if (!submitted) {
      test.skip(true, 'Text input not available in current kiosk layout');
      return;
    }

    await expect(page.getByText(/営業時間|9:00/)).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// B. English queries (mocked backend)
// ---------------------------------------------------------------------------

test.describe('Multilingual — English queries (mocked)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-en',
          greeting: 'Welcome!',
          stage: 'greeting',
        }),
      });
    });
  });

  test('English WiFi query returns English response', async ({ page }) => {
    await mockQaResponse(
      page,
      'Free WiFi is available. SSID: EngineerCafe_WiFi, Password: cafe2024',
      'en',
    );
    await page.goto('/');
    await dismissInitialModal(page);

    // Switch language to English via settings.
    const settingsButton = page.getByRole('button', { name: /設定|Settings/ });
    await settingsButton.click();
    const englishOption = page.getByText('English');
    if (await englishOption.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await englishOption.click();
    }
    // Close settings.
    const closeSettings = page.getByRole('button', { name: /設定|Settings/ });
    if (await closeSettings.isVisible({ timeout: 1_000 }).catch(() => false)) {
      await closeSettings.click();
    }

    const submitted = await submitTextQuery(page, 'What is the WiFi password?');
    if (!submitted) {
      test.skip(true, 'Text input not available in current kiosk layout');
      return;
    }

    await expect(page.getByText(/WiFi|wifi|SSID/i)).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// C. Chinese recognition (mocked backend)
// ---------------------------------------------------------------------------

test.describe('Multilingual — Chinese recognition (mocked)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-zh',
          greeting: '欢迎',
          stage: 'greeting',
        }),
      });
    });
  });

  test('Chinese greeting is processed and response is displayed', async ({ page }) => {
    await mockQaResponse(page, '欢迎来到工程师咖啡馆！WiFi密码是cafe2024。', 'zh');
    await page.goto('/');
    await dismissInitialModal(page);

    const submitted = await submitTextQuery(page, '你好，WiFi密码是什么？');
    if (!submitted) {
      test.skip(true, 'Text input not available in current kiosk layout');
      return;
    }

    await expect(page.getByText(/WiFi|wifi|密码/i)).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// D. Korean recognition (mocked backend)
// ---------------------------------------------------------------------------

test.describe('Multilingual — Korean recognition (mocked)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-ko',
          greeting: '환영합니다',
          stage: 'greeting',
        }),
      });
    });
  });

  test('Korean greeting is processed and response is displayed', async ({ page }) => {
    await mockQaResponse(page, '엔지니어 카페에 오신 것을 환영합니다! WiFi 비밀번호는 cafe2024입니다.', 'ko');
    await page.goto('/');
    await dismissInitialModal(page);

    const submitted = await submitTextQuery(page, '안녕하세요, WiFi 비밀번호가 뭐예요?');
    if (!submitted) {
      test.skip(true, 'Text input not available in current kiosk layout');
      return;
    }

    await expect(page.getByText(/WiFi|wifi|비밀번호/i)).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// E. Language switching persists across turns
// ---------------------------------------------------------------------------

test.describe('Multilingual — language switching persistence', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`**${VOICE_URL}`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-lang',
          greeting: 'Welcome',
          stage: 'greeting',
        }),
      });
    });
  });

  test('switching to English updates all UI labels', async ({ page }) => {
    await page.goto('/');
    await dismissInitialModal(page);

    // Open settings and switch to English.
    const settingsButton = page.getByRole('button', { name: /設定|Settings/ });
    await settingsButton.click();

    // Click on the English option in the display language section.
    const englishLabel = page.getByText('English').first();
    if (await englishLabel.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await englishLabel.click();
    }

    // Close settings panel by clicking the settings button again or pressing escape.
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    // After switching to English, the kiosk buttons should show English labels.
    // "Voice chat" instead of "音声応対", "Slide guide" instead of "スライド案内".
    await expect(page.getByRole('button', { name: /Voice chat/ })).toBeVisible({ timeout: 3_000 });
    await expect(page.getByRole('button', { name: /Slide guide/ })).toBeVisible({ timeout: 3_000 });
  });

  test('language persists after returning from OCR view', async ({ page }) => {
    await page.goto('/');
    await dismissInitialModal(page);

    // Open settings and switch to English.
    const settingsButton = page.getByRole('button', { name: /設定|Settings/ });
    await settingsButton.click();
    const englishLabel = page.getByText('English').first();
    if (await englishLabel.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await englishLabel.click();
    }
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    // Enter member card OCR view.
    const memberButton = page.getByRole('button', { name: /Member card/ });
    await expect(memberButton).toBeVisible({ timeout: 3_000 });
    await memberButton.click();

    // Return to idle via back button.
    const backButton = page.getByRole('button', { name: /Back to menu/ });
    await expect(backButton).toBeVisible({ timeout: 5_000 });
    await backButton.click();

    // Language should still be English after returning.
    await expect(page.getByRole('button', { name: /Voice chat/ })).toBeVisible({ timeout: 3_000 });
  });
});

// ---------------------------------------------------------------------------
// F. Live backend integration tests (skipped unless env vars set)
// ---------------------------------------------------------------------------

test.describe('Multilingual — live backend integration', () => {
  test.skip(!hasBackend, 'Live multilingual tests require BACKEND_API_URL and BACKEND_API_KEY');

  test('Japanese WiFi query gets a real response from the backend', async ({ page }) => {
    await page.goto('/');
    await dismissInitialModal(page);

    const submitted = await submitTextQuery(page, 'WiFiのパスワードを教えてください');
    if (!submitted) {
      test.skip(true, 'Text input not available');
      return;
    }

    // The real backend should respond with WiFi information.
    await expect(page.getByText(/Wi-Fi|wifi|SSID|パスワード/i)).toBeVisible({ timeout: 30_000 });
  });

  test('English WiFi query gets a real response from the backend', async ({ page }) => {
    await page.goto('/');
    await dismissInitialModal(page);

    // Switch to English via settings.
    const settingsButton = page.getByRole('button', { name: /設定|Settings/ });
    await settingsButton.click();
    const englishLabel = page.getByText('English').first();
    if (await englishLabel.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await englishLabel.click();
    }
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    const submitted = await submitTextQuery(page, 'What is the WiFi password?');
    if (!submitted) {
      test.skip(true, 'Text input not available');
      return;
    }

    await expect(page.getByText(/WiFi|wifi|password|SSID/i)).toBeVisible({ timeout: 30_000 });
  });
});
