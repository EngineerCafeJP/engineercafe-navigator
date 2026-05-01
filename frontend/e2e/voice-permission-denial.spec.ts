import { expect, test } from '@playwright/test';

/**
 * Alpha #638 — getUserMedia rejection UX (WebKit project in playwright.config).
 */

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await closeButton.click({ force: true }).catch(() => {});
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

async function installMicDenial(page: import('@playwright/test').Page, errorName: string) {
  await page.addInitScript((name: string) => {
    const md = navigator.mediaDevices ?? {};
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        ...md,
        getUserMedia: async () => {
          throw new DOMException('Playwright injected denial', name);
        },
      },
    });
  }, errorName);
}

test.describe('Microphone permission denial (#638)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-permission',
          greeting: 'テストです。',
          stage: 'greeting',
        }),
      });
    });
    await page.route('**/api/voice', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });
  });

  async function assertMicDeniedRecovery(page: import('@playwright/test').Page) {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    const voiceButton = page.getByTestId('kiosk-voice-button');
    await voiceButton.click();

    await expect(page.getByTestId('kiosk-voice-status')).toContainText(/マイク|Microphone|HTTPS|許可|permission/i, {
      timeout: 8_000,
    });

    await expect.poll(async () => (await voiceButton.textContent()) ?? '').not.toMatch(/録音中|Recording/, {
      timeout: 8_000,
    });
  }

  test('NotAllowedError shows guidance and clears recording affordance', async ({ page }) => {
    await installMicDenial(page, 'NotAllowedError');
    await assertMicDeniedRecovery(page);
  });

  test('NotFoundError shows guidance', async ({ page }) => {
    await installMicDenial(page, 'NotFoundError');
    await assertMicDeniedRecovery(page);
  });

  test('InvalidStateError shows guidance', async ({ page }) => {
    await installMicDenial(page, 'InvalidStateError');
    await assertMicDeniedRecovery(page);
  });

  test('SecurityError shows HTTPS guidance', async ({ page }) => {
    await installMicDenial(page, 'SecurityError');
    await assertMicDeniedRecovery(page);
  });
});
