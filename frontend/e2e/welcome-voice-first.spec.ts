import { expect, test } from '@playwright/test';

const RECEPTION_START_URL = '/api/reception/start';

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click({ force: true }).catch(() => {});
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

function mockReceptionStart(page: import('@playwright/test').Page) {
  return page.route(`**${RECEPTION_START_URL}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reception_session_id: 'mock-welcome-voice-first',
        greeting: 'エンジニアカフェへようこそ！ご用件をお聞かせください。',
        stage: 'greeting',
      }),
    });
  });
}

test.describe('Welcome voice-first (#616)', () => {
  test.beforeEach(async ({ page }) => {
    await mockReceptionStart(page);
    await page.route('**/api/qa', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, answer: 'OK', emotion: 'neutral', metadata: {} }),
      });
    });
    await page.route('**/api/voice', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);
  });

  test('idle kiosk shows session mode badge without OCR overlay', async ({ page }) => {
    await expect(page.getByTestId('kiosk-voice-mode-badge')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden();
  });

  test('Welcome opens reception voice lane without welcome OCR overlay', async ({ page }) => {
    await page.getByRole('button', { name: 'Welcome' }).click();
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect(page.getByTestId('response-text')).toContainText('エンジニアカフェへようこそ', {
      timeout: 8_000,
    });
  });
});
