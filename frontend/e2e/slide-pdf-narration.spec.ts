import { expect, test } from '@playwright/test';
import { setupWebAudioMock } from './helpers/mocks';

async function dismissInitialModal(page: import('@playwright/test').Page) {
  const modal = page.getByRole('dialog');
  const closeButton = page.getByTestId('initial-settings-close');
  if (await closeButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await page.waitForTimeout(1_500);
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline && !(await modal.isHidden().catch(() => false))) {
      await closeButton.click({ timeout: 1_000, force: true }).catch(() => {});
      if (!(await modal.isHidden().catch(() => false))) {
        await closeButton
          .evaluate((button) => {
            if (button instanceof HTMLButtonElement) {
              button.click();
            }
          })
          .catch(() => {});
      }
      await page.waitForTimeout(250);
    }
    await expect(modal).toBeHidden({ timeout: 10_000 });
  }
  await expect(page.getByRole('button', { name: 'Welcome' })).toBeVisible({ timeout: 5_000 });
}

test.describe('Slide PDF narration deck (#624)', () => {
  test('autoplay uses static slide audio and does not call Piper TTS', async ({ page }) => {
    await setupWebAudioMock(page);
    await page.route('**/api/reception/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reception_session_id: 'mock-slide-narration',
          greeting: 'テストです。',
          stage: 'greeting',
        }),
      });
    });

    let piperHits = 0;

    await page.route('**/api/voice', async (route) => {
      const req = route.request();
      if (req.method() !== 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        return;
      }
      let body: Record<string, unknown> = {};
      try {
        body = req.postDataJSON() as Record<string, unknown>;
      } catch {
        body = {};
      }
      if (body.action === 'text_to_speech') {
        piperHits++;
        await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await dismissInitialModal(page);

    await page.setViewportSize({ width: 960, height: 540 });
    await page.getByTestId('kiosk-slides-button').click();
    await page.getByTestId('slide-language-ja').click();

    await expect(page.getByTestId('reception-pdf-counter')).toHaveText('1 / 5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('reception-pdf-play')).toHaveAttribute('data-state', 'playing', {
      timeout: 15_000,
    });

    await page.waitForTimeout(3_000);
    expect(piperHits).toBe(0);
  });
});
