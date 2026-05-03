import { expect, test } from '@playwright/test';

const RECEPTION_START_URL = '/api/reception/start';

interface MediaRequestCounts {
  audio: number;
  video: number;
}

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click({ force: true }).catch(() => {});
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function installMediaRequestProbe(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    const counts = { audio: 0, video: 0 };
    const existingMediaDevices = navigator.mediaDevices ?? {};

    Object.defineProperty(window, '__welcomeMediaRequestCounts', {
      configurable: true,
      value: counts,
    });

    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        ...existingMediaDevices,
        getUserMedia: async (constraints?: MediaStreamConstraints) => {
          const wantsVideo = Boolean(
            constraints &&
              typeof constraints === 'object' &&
              'video' in constraints &&
              constraints.video,
          );
          const wantsAudio = Boolean(
            constraints &&
              typeof constraints === 'object' &&
              'audio' in constraints &&
              constraints.audio,
          );

          if (wantsVideo) {
            counts.video += 1;
            return new Promise<MediaStream>(() => {
              // Keep OCR mounted without requiring real camera access.
            });
          }
          if (wantsAudio) {
            counts.audio += 1;
          }
          return new MediaStream();
        },
      },
    });
  });
}

async function getMediaRequestCounts(
  page: import('@playwright/test').Page,
): Promise<MediaRequestCounts> {
  return page.evaluate(() => {
    const windowWithCounts = window as Window & {
      __welcomeMediaRequestCounts?: MediaRequestCounts;
    };
    return windowWithCounts.__welcomeMediaRequestCounts ?? { audio: 0, video: 0 };
  });
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
    await installMediaRequestProbe(page);
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

  test('Welcome does not request camera; member card button does', async ({ page }) => {
    expect((await getMediaRequestCounts(page)).video).toBe(0);

    await page.getByRole('button', { name: 'Welcome' }).click();
    await expect(page.getByTestId('kiosk-welcome-ocr-overlay')).toBeHidden({ timeout: 5_000 });
    await expect
      .poll(async () => (await getMediaRequestCounts(page)).video, { timeout: 2_000 })
      .toBe(0);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.getByRole('button', { name: /会員証|Member card/ }).click();
    await expect
      .poll(async () => (await getMediaRequestCounts(page)).video, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(1);
  });
});
